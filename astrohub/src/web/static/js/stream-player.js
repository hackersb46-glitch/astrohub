/**
 * stream-player.js - MediaMTX WHEP 流播放器
 *
 * 架构: IPC摄像头 → GStreamer(纯中继) → MediaMTX(:8554) → WHEP(:8889) → 浏览器
 *
 * WHEP 流程:
 *   1. POST SDP offer → /{path}/whep → 收到 SDP answer + Location header
 *   2. PATCH ICE candidates → /{path}/whep/{id}
 *   Ice 候选在 POST 成功前可能已收集 → 缓存后批量发送
 */

class StreamPlayer {
    constructor(canvas, video) {
        this._canvas = canvas;
        this._video = video;
        this._pc = null;
        this._mediaStream = null;
        this._streamId = 'default';
        this._rtspUrl = null;
        this._state = 'stopped';
        this._pathName = 'cam01';
        this._resourceId = null;
        this._connected = false;
        this._iceBuffer = []; // 未发送的 ICE 候选缓存

        this.onStateChange = null;
        this.onError = null;

        this._mediaMTXHost = window.location.hostname || '127.0.0.1';
        this._mediaMTXPort = 8889;

        if (this._video) {
            this._video.muted = true;
            this._video.playsInline = true;
        }
    }

    get state() { return this._state; }

    _setState(s) {
        this._state = s;
        if (this.onStateChange) this.onStateChange(s);
    }

    _whepUrl() {
        return `http://${this._mediaMTXHost}:${this._mediaMTXPort}/${this._pathName}/whep`;
    }

    async start(rtspUrl, options) {
        this._cleanupWHEP();
        this._mediaStream = null;
        this._connected = false;
        this._iceBuffer = [];
        if (this._video) this._video.srcObject = null;

        this._rtspUrl = rtspUrl;
        this._setState('connecting');

        try {
            // 1. 启动后端 GStreamer 推流
            const resp = await fetch('/api/v1/stream/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stream_id: this._streamId, rtsp_url: rtspUrl }),
            });

            if (resp.status === 409) {
                console.log('[StreamPlayer] Stream already running, continuing...');
            } else if (!resp.ok) {
                const errText = await resp.text().catch(() => '');
                throw new Error('流启动失败 (' + resp.status + '): ' + errText);
            } else {
                const state = await resp.json();
                if (!state.gstAlive) throw new Error('流启动失败: ' + (state.error || 'unknown'));
            }

            // 2. WHEP 信令交换（内含 retry，不额外等待）
            await this._whepExchange();

            this._setState('connected');
        } catch (e) {
            console.error('[StreamPlayer] start error:', e);
            this._setState('disconnected');
            if (this.onError) this.onError(e.message || String(e));
        }
    }

    async stop() {
        this._cleanupWHEP();
        this._mediaStream = null;
        this._connected = false;
        this._iceBuffer = [];
        if (this._video) this._video.srcObject = null;
        this._setState('stopped');

        try {
            await fetch('/api/v1/stream/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stream_id: this._streamId }),
            });
        } catch (_) {}
    }

    _cleanupWHEP() {
        // 删除旧 WHEP 资源（MediaMTX 侧）
        if (this._resourceId) {
            try {
                fetch(`${this._whepUrl()}/${this._resourceId}`, { method: 'DELETE' });
            } catch (_) {}
            this._resourceId = null;
        }
        // 关闭旧 PeerConnection
        if (this._pc) {
            try { this._pc.close(); } catch (_) {}
            this._pc = null;
        }
        this._iceBuffer = [];
    }

    _createPC() {
        const pc = new RTCPeerConnection({
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });

        pc.onicecandidate = (e) => this._onIceCandidate(e);
        pc.ontrack = (e) => this._onTrackReceived(e);
        pc.onconnectionstatechange = () => this._onConnectionState();
        pc.oniceconnectionstatechange = () => {
            console.log('[StreamPlayer] ICE:', pc.iceConnectionState);
        };

        pc.addTransceiver('video', { direction: 'recvonly' });
        return pc;
    }

    async _whepExchange() {
        this._pc = this._createPC();
        const offer = await this._pc.createOffer();
        await this._pc.setLocalDescription(offer);

        // 重试 POST 直到流就绪，复用同一 SDP（不重建 PC）
        for (let attempt = 0; attempt < 50; attempt++) {
            try {
                const resp = await fetch(this._whepUrl(), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/sdp' },
                    body: this._pc.localDescription.sdp,
                    mode: 'cors',
                });

                if (resp.ok) {
                    const answerSdp = await resp.text();
                    const loc = resp.headers.get('location');
                    const rid = loc ? loc.split('/').pop() : null;

                    await this._pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });

                    // 成功：发送缓存的 ICE 候选
                    this._resourceId = rid;
                    await this._flushIceBuffer();
                    return;
                }

                if (attempt === 0 || attempt % 10 === 0) {
                    console.log(`[StreamPlayer] WHEP retry ${attempt+1}/50: ${resp.status}`);
                }

                if (resp.status === 404 || resp.status >= 500) {
                    await new Promise(r => setTimeout(r, 50));
                    continue;
                }

                const errText = await resp.text().catch(() => '');
                throw new Error('WHEP POST ' + resp.status + ': ' + errText);

            } catch (e) {
                if (e.name === 'TypeError' ||
                    e.message.includes('Failed to fetch') ||
                    e.message.includes('NetworkError')) {
                    await new Promise(r => setTimeout(r, 50));
                    continue;
                }
                throw e;
            }
        }
        throw new Error('WHEP 超时: 流始终未就绪');
    }

    _onIceCandidate(e) {
        if (!e.candidate) return;
        if (this._resourceId) {
            // 已有 resourceId → 直接发送
            this._sendIceCandidates([e.candidate]);
        } else {
            // 缓存起来，等 resourceId 就绪后批量发送
            this._iceBuffer.push(e.candidate);
        }
    }

    async _flushIceBuffer() {
        if (this._iceBuffer.length === 0) return;
        const batch = this._iceBuffer.splice(0);
        await this._sendIceCandidates(batch);
    }

    async _sendIceCandidates(candidates) {
        if (!this._resourceId) return;
        const body = {
            candidates: candidates.map(c => ({
                candidate: c.candidate,
                sdpMid: c.sdpMid,
                sdpMLineIndex: c.sdpMLineIndex,
            }))
        };
        try {
            await fetch(`${this._whepUrl()}/${this._resourceId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/trickle-ice-candidates' },
                body: JSON.stringify(body),
                mode: 'cors',
            });
        } catch (err) {
            console.warn('[StreamPlayer] ICE PATCH failed:', err);
        }
    }

    _onTrackReceived(e) {
        if (this._mediaStream) return;
        this._mediaStream = e.streams[0];
        if (this._video) {
            this._video.srcObject = this._mediaStream;
            this._video.play().catch(e => console.warn('[StreamPlayer] autoplay:', e));
        }
        this._setState('playing');
    }

    _onConnectionState() {
        if (!this._pc) return;
        const st = this._pc.connectionState;
        console.log('[StreamPlayer] Connection state:', st);
        if (st === 'connected') this._connected = true;
        if (st === 'disconnected' || st === 'failed') {
            this._connected = false;
            this._setState('disconnected');
        }
    }
}

// v8.84: 浏览器环境暴露到全局
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { StreamPlayer };
} else if (typeof window !== 'undefined') {
    window.StreamPlayer = StreamPlayer;
}