"""Test gain oscillation detection - v8.68"""
from src.controlpanel.brightness import IterativeBrightness

sv = ['1/25','1/50','1/75','1/100','1/120','1/150','1/175','1/200','1/225','1/250',
      '1/300','1/425','1/600','1/1000','1/1250','1/1750','1/2500','1/3500','1/6000',
      '1/10000','1/30000']
iv = ['160','200','240','280','340','400','480','560','680','960','1100','1400','1600','1900','2200']

print("=" * 60)
print("Test 1: gain oscillation 3 times -> rollback")
print("=" * 60)

ib = IterativeBrightness(target=50, shutter_idx=18, iris_idx=10, gain=20,
                          shutter_values=sv, iris_values=iv, gain_min=0, gain_max=100)
ib._shutter_frozen = True
ib._iris_frozen = True

# Simulate: gain from 20, brightness crosses target 3 times
brightness_seq = [
    (30.0, "step 0, below target"),
    (49.0, "step 1, below target, side=-1"),
    (51.0, "step 2, above target, side=+1, osc=1"),
    (48.0, "step 3, below target, side=-1, osc=2"),
    (52.0, "step 4, above target, side=+1, osc=3 -> ROLLBACK!"),
]

for i, (b, desc) in enumerate(brightness_seq):
    result = ib.step(b)
    if result['action'] == 'stop':
        print(f"Step {i}: brightness={b:.1f} ({desc}) gain={result['gain']:3d} action=stop")
        print(f"  reason={result.get('reason')} msg={result['message']}")
        break
    print(f"Step {i}: brightness={b:.1f} ({desc}) gain={result['gain']:3d} action={result['action']}")

print("\n" + "=" * 60)
print("Test 2: target=0 gain hits limit -> success")
print("=" * 60)

ib2 = IterativeBrightness(target=0, shutter_idx=18, iris_idx=10, gain=10,
                           shutter_values=sv, iris_values=iv, gain_min=0, gain_max=100)
ib2._shutter_frozen = True
ib2._iris_frozen = True

for i, b in enumerate([0.6, 0.3, 0.1]):
    result = ib2.step(b)
    if result['action'] == 'stop':
        print(f"Step {i}: brightness={b:.1f} gain={result['gain']:3d} action=stop reason={result.get('reason')}")
        break

print("\n" + "=" * 60)
print("Test 3: target=100 gain hits limit -> success")
print("=" * 60)

ib3 = IterativeBrightness(target=100, shutter_idx=18, iris_idx=10, gain=85,
                           shutter_values=sv, iris_values=iv, gain_min=0, gain_max=100)
ib3._shutter_frozen = True
ib3._iris_frozen = True

for i, b in enumerate([99.2, 99.5, 99.8]):
    result = ib3.step(b)
    if result['action'] == 'stop':
        print(f"Step {i}: brightness={b:.1f} gain={result['gain']:3d} action=stop reason={result.get('reason')}")
        break

print("\n" + "=" * 60)
print("Test 4: target=50 gain hits limit w/o oscillation -> failure")
print("=" * 60)

ib4 = IterativeBrightness(target=50, shutter_idx=18, iris_idx=10, gain=90,
                           shutter_values=sv, iris_values=iv, gain_min=0, gain_max=100)
ib4._shutter_frozen = True
ib4._iris_frozen = True

for i, b in enumerate([40.0, 42.0, 44.0, 46.0]):
    result = ib4.step(b)
    if result['action'] == 'stop':
        print(f"Step {i}: brightness={b:.1f} gain={result['gain']:3d} action=stop reason={result.get('reason')}")
        break

print("\nAll tests done.")
