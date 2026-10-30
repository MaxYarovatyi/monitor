import random, socket, time
LAN, LOSS = "192.168.198.28", 0.01
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rx.bind(("127.0.0.1", 6000))
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LAN))
n = dropped = 0; t = time.time()
while True:
    d = rx.recv(65536); n += 1
    if random.random() > LOSS:
        tx.sendto(d, ("239.255.10.1", 5000))
    else:
        dropped += 1
    if time.time() - t > 2:
       print(f"отримано {n}, відкинуто {dropped}"); t = time.time()