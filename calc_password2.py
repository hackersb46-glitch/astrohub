import hashlib

# 从摄像头获取的值
sessionID = 'a73029ec404b20abf68702009654d6f6876735c6f41751bda9df3b5538ece973'
challenge = '35c0d5e708a372059e773018bcfab73c'
iterations = 100
salt = '97774dbe5bed08536f53132ac6bd19ae4f090036fdd88e3b5b3376eea30d63fa'
username = 'admin'
password = 'Nftw1357'

# SDK 的加密方式: sha256(username + salt + password)
key = hashlib.sha256((username + salt + password).encode()).hexdigest()
key = hashlib.sha256((key + challenge).encode()).hexdigest()
for i in range(iterations - 2):
    key = hashlib.sha256(key.encode()).hexdigest()

print(f'Encrypted password: {key}')