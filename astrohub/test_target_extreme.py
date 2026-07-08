from src.controlpanel.brightness import IterativeBrightness

sv = ['1/25','1/50','1/75','1/100','1/120','1/150','1/175','1/200','1/225','1/250',
      '1/300','1/425','1/600','1/1000','1/1250','1/1750','1/2500','1/3500','1/6000',
      '1/10000','1/30000']
iv = ['160','200','240','280','340','400','480','560','680','960','1100','1400','1600','1900','2200']

def simulate(target):
    ib = IterativeBrightness(target=target, shutter_idx=0, iris_idx=0, gain=0,
                              shutter_values=sv, iris_values=iv)
    brightness = 99.5
    for i in range(100):
        cmd = ib.step(brightness)
        if cmd['action'] == 'stop':
            print(f'target={target}: STOP after {i+1} steps, reason={cmd["reason"]}, brightness={cmd["brightness"]:.1f}, shutter={cmd["shutter"]}, iris={cmd["iris"]}, gain={cmd["gain"]}')
            return
        if cmd['action'] == 'set_shutter':
            brightness = max(0, brightness - 5)  # Simulate brightness decrease
        elif cmd['action'] == 'set_iris':
            brightness = max(0, brightness - 3)
        elif cmd['action'] == 'set_gain':
            brightness = max(0, brightness - 1)
    print(f'target={target}: REACHED MAX STEPS, shutter_idx={ib._shutter_idx}, iris_idx={ib._iris_idx}, gain={ib._gain}')

print('=== Testing target=0 ===')
simulate(0)
print()
print('=== Testing target=100 ===')
simulate(100)
