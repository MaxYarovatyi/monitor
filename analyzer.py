import socket
import time
from urllib.parse import urlparse

def stream_file_to_multiple_udp(file_path, udp_urls, chunk_size=1024, delay=0.001):
    """
    Перетворює файл на потік і транслює його одночасно на кілька UDP URL.
    """
    # 1. Парсимо всі URL та збираємо пари (IP, PORT)
    targets = []
    for url in udp_urls:
        parsed = urlparse(url)
        if parsed.scheme != 'udp':
            print(f"Пропущено некоректний URL (не UDP): {url}")
            continue
        targets.append((parsed.hostname, parsed.port))
    
    if not targets:
        print("Немає валідних адрес для відправки.")
        return

    # 2. Створюємо один сокет для трансляції на всі напрямки
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print(f"Початок трансляції файлу '{file_path}'...")
    print(f"Потік дублюється на {len(targets)} адрес(и):")
    for ip, port in targets:
        print(f" -> {ip}:{port}")
    
    try:
        # 3. Відкриваємо файл як бінарний потік
        with open(file_path, "rb") as f:
            packet_count = 0
            
            while True:
                # Читаємо один шматок файлу
                chunk = f.read(chunk_size)
                if not chunk:
                    break  # Файл закінчився
                
                # 4. РЕТРАНСЛЯЦІЯ: відправляємо цей шматок ВСІМ отримувачам
                for ip, port in targets:
                    try:
                        sock.sendto(chunk, (ip, port))
                    except Exception as e:
                        # Якщо одна адреса недоступна, це не має зупиняти відправку іншим
                        print(f"Помилка відправки на {ip}:{port}: {e}")
                
                packet_count += 1
                
                # Мікропауза для стабільності UDP-потоку
                if delay > 0:
                    time.sleep(delay)
                    
        print(f"\nТрансляцію завершено! Надіслано пакетів: {packet_count}")
        
    except FileNotFoundError:
        print(f"Помилка: Файл '{file_path}' не знайдено.")
    finally:
        sock.close()

# --- ПРИКЛАД ВИКОРИСТАННЯ ---

# Список ваших UDP URL (різні IP, різні порти — як завгодно)
UDP_TARGET_URLS = [
    "udp://222.0.0.38:1234",
    "udp://222.0.0.38:1233",
    "udp://222.0.0.38:1232",
    "udp://222.0.0.38:1231",
    "udp://222.0.0.38:1230",
]

FILE_TO_STREAM = "sample.ts"  # Ваш файл (відео, аудіо, бінарний потік)

# Запуск трансляції
stream_file_to_multiple_udp(
    file_path=FILE_TO_STREAM, 
    udp_urls=UDP_TARGET_URLS, 
    chunk_size=1024, 
    delay=0.001
)
