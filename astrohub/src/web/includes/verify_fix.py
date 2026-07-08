import sys

with open('console.html', 'r', encoding='utf-8') as f:
    c = f.read()

print('API调用检查:')
print('  setShutterSpeed:', c.count('setShutterSpeed(s.'))
print('  setIris:', c.count('setIris(s.'))
print('  setExposureMode:', c.count('setExposureMode(s.'))
print('  setWhiteBalanceGain:', c.count('setWhiteBalanceGain('))
print('  setNoiseReduce:', c.count('setNoiseReduce('))
print('  setSharpness:', c.count('setSharpness(s.'))
print('  apiPut image/settings:', c.count("apiPut('/api/v1/ptz/' + deviceIp + '/image/settings'"))
print()
print('typo修复:', "dnrTemporal');n" not in c)
print('updateShutterIrisState:', c.count('updateShutterIrisState()') > 0)
