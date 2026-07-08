import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.controlpanel.autofocus import ContrastAF

# Test: 老板数据 (best at pos 4, scan to pos 7)
af = ContrastAF()
contrasts = [79.97, 87.71, 97.49, 160.00, 329.41, 120.70, 94.01, 329.41]
for i, c in enumerate(contrasts):
    cmd = af.step(c)
    action = cmd['action']
    stage = cmd['stage']
    dur = cmd['duration']
    msg = cmd['message'].encode('ascii', 'replace').decode()
    print(f"step {i+1}: c={c} -> {action}, {stage}, dur={dur}, msg={msg}")
    if cmd['action'] == 'stop':
        break
    if stage in ('approach1', 'approach2'):
        print(f"  --- {stage} phase ---")
        for j in range(15):
            sim_c = 329.0 + (j * 2 if stage == 'approach2' else 0)
            cmd = af.step(sim_c)
            action = cmd['action']
            stage2 = cmd['stage']
            msg = cmd['message'].encode('ascii', 'replace').decode()
            print(f"  {stage} {j+1}: c={sim_c} -> {action}, {stage2}, msg={msg}")
            if cmd['action'] == 'stop':
                break
        break

# Test: 阈值50检查
print("\n=== Threshold test ===")
af2 = ContrastAF()
# best=45 < 50, should not trigger fit
low_contrasts = [30, 35, 45, 40, 38, 35, 33]
for i, c in enumerate(low_contrasts):
    cmd = af2.step(c)
    stage = cmd['stage']
    msg = cmd['message'].encode('ascii', 'replace').decode()
    print(f"  step {i+1}: c={c} -> {stage}, msg={msg}")
    if cmd['action'] == 'stop':
        break
