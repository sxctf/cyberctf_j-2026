#!/usr/bin/env python3
                       
"""
Терминал "ШИФРАТОР" — законсервированный шифровальный узел объекта №17.
CTF Jeopardy / crypto / medium.

Две ступени атаки, сцепленные в цепочку:
  1) AES-ECB oracle (пункт 3) незаметно дописывает кодовую фразу оператора.
     Побайтовое восстановление (byte-at-a-time) даёт пароль -> авторизация (пункт 7).
  2) После авторизации архивный шифроканал (пункт 8) работает в потоковом режиме
     с ПОСТОЯННОЙ гаммой (nonce reuse). XOR с шифротекстом секретной депеши (пункт 2)
     снимает флаг.

Исходник участникам НЕ раздаётся — это удалённый оракул. Раздаётся только адрес.
"""

import os
import socket
import socketserver
import threading
import secrets
import string

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

                                                                               
                         
                                                                               

FLAG = os.environ.get("FLAG", "flag{n0nc3_r3us3_pl_us_3cb_l3ak_th3_arch1v3}").encode()

                                                                    
_K_ECB = secrets.token_bytes(16)                                                
_K_CTR = secrets.token_bytes(16)                                 
_IV_CTR = secrets.token_bytes(16)                                                   

                                                                        
def _gen_passphrase() -> bytes:
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(16))
    return ("ST-OPERATOR-" + body).encode()

_PASSPHRASE = _gen_passphrase()

                                                                                     
_SECRET_DESPATCH_PLAINTEXT = (
    "ГРИФ: ОСОБОЙ ВАЖНОСТИ. Инв. №0451.\n"
    "Кодовое слово для канала связи Центра: " + FLAG.decode() + "\n"
    "По прочтении — уничтожить."
).encode("utf-8")

                                                                               
                  
                                                                               

def _pkcs7(data: bytes) -> bytes:
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def ecb_encrypt(key: bytes, data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(_pkcs7(data)) + enc.finalize()


def _ecb_block(key: bytes, block16: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(block16) + enc.finalize()


def _keystream(key: bytes, iv: bytes, n: int) -> bytes:
    """Гамма CTR: E_k(iv), E_k(iv+1), ... Так как iv постоянна — гамма повторяется."""
    out = bytearray()
    ctr = int.from_bytes(iv, "big")
    while len(out) < n:
        out += _ecb_block(key, (ctr % (1 << 128)).to_bytes(16, "big"))
        ctr += 1
    return bytes(out[:n])


def ctr_crypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    ks = _keystream(key, iv, len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


                                                            
_SECRET_CIPHERTEXT = ctr_crypt(_K_CTR, _IV_CTR, _SECRET_DESPATCH_PLAINTEXT)

                                                                               
                    
                                                                               

BANNER = r"""
+--------------------------------------------------------------+
|   ####  #  # # ####  ####   ###  ####  ###  ####             |
|   #     #  # # #   # #   # #   #   #   #   # #   #            |
|   ###   #### # ####  ####  #####   #   #   # ####            |
|   #     #  # # #     #  #  #   #   #   #   # #  #             |
|   #     #  # # #     #   # #   #   #   ###  #   #            |
|                                                              |
|         ОБЪЕКТ №17 · УЗЕЛ КРИПТОГРАФИЧЕСКОЙ СВЯЗИ            |
|            криптомодуль "ВОЛХВ-3"  ·  ревизия 3.1            |
+--------------------------------------------------------------+
   [СИСТЕМА] Питание восстановлено. Модуль в рабочем режиме.
   [СИСТЕМА] Последнее ТО: 14.11.1989. Регламент не соблюдён.
"""

MENU = """
------------------------- ТЕРМИНАЛ ---------------------------
 [1] Опись архива депеш
 [2] Прочитать депешу (по инв. номеру)
 [3] Зашифровать сообщение
 [4] Расшифровать сообщение
 [5] Сведения о криптомодуле
 [6] Журнал последних операций
 [7] Авторизация старшего оператора
 [8] Архивный канал             (требуется авторизация)
 [0] Отключиться
--------------------------------------------------------------
"""

INVENTORY = """\
   ИНВ.       ДАТА         ГРИФ                СТАТУС
   --------   ----------   -----------------   ------------------
   0198       03.02.1988   служебная           [РАССЕКРЕЧЕНО]
   0231       17.06.1988   для сл. пользования  [РАССЕКРЕЧЕНО]
   0307       25.09.1988   секретно             [РАССЕКРЕЧЕНО]
   0451       ??.??.19??   ОСОБОЙ ВАЖНОСТИ      [ГРИФ · ЗАКРЫТО]"""

OPEN_DESPATCHES = {
    "0198": "Плановая проверка линии связи Л-4. Замечаний нет.",
    "0231": "Запрос на поставку перфоленты. Отправлено в снабжение.",
    "0307": "Учения 'Гроза-88' завершены. Личный состав к службе годен.",
}

MODULE_INFO = """\
   КРИПТОМОДУЛЬ "ВОЛХВ-3"
   -----------------------------------------------------------
   Состояние ................. рабочее
   Блок шифрования ........... исправен, самотест пройден
   Архивный канал ............ доступен старшему оператору
   Последняя калибровка ...... 14.11.1989
   -----------------------------------------------------------
"""

JOURNAL = """\
   ЖУРНАЛ ОПЕРАЦИЙ (последние записи)
   14.11.1989 09:12  шифрование служебной сводки .......... ОК
   14.11.1989 09:41  обращение к архиву депеш ............. ОК
   14.11.1989 10:03  плановое ТО ....................... ПРОПУЩЕНО
"""

                                                                               
                        
                                                                               

class Terminal:
    def __init__(self, rfile, wfile):
        self.rfile = rfile
        self.wfile = wfile
        self.authorized = False

    def send(self, text: str = "") -> None:
        self.wfile.write((text + "\n").encode("utf-8"))
        self.wfile.flush()

    def prompt(self, text: str) -> str:
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()
        line = self.rfile.readline()
        if not line:
            raise EOFError
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

                                                                               

    def op_inventory(self):
        self.send(INVENTORY)

    def op_read(self):
        num = self.prompt("   Инв. номер депеши> ").strip()
        if num in OPEN_DESPATCHES:
            self.send("   [ДЕПЕША %s]" % num)
            self.send("   " + OPEN_DESPATCHES[num])
        elif num == "0451":
            if not self.authorized:
                self.send("   [ОТКАЗ] Депеша 0451 под грифом ОСОБОЙ ВАЖНОСТИ.")
                self.send("   [ОТКАЗ] Требуется авторизация старшего оператора (пункт 7).")
            else:
                self.send("   [ДЕПЕША 0451 · ГРИФ ОСОБОЙ ВАЖНОСТИ]")
                self.send("   Открытый текст к выдаче ЗАПРЕЩЁН регламентом.")
                self.send("   Доступен только зашифрованный образ депеши (hex):")
                self.send("   " + _SECRET_CIPHERTEXT.hex())
        else:
            self.send("   [ОШИБКА] Депеша с таким номером не найдена.")

    def op_encrypt(self):
        msg = self.prompt("   Текст сообщения> ")
        data = msg.encode("utf-8")
                                                                                  
        ct = ecb_encrypt(_K_ECB, data + _PASSPHRASE)
        self.send("   Шифротекст (hex): " + ct.hex())

    def op_decrypt(self):
        hx = self.prompt("   Шифротекст (hex)> ").strip()
        try:
            ct = bytes.fromhex(hx)
            if len(ct) == 0 or len(ct) % 16 != 0:
                raise ValueError
        except ValueError:
            self.send("   [ОШИБКА] Неверный формат блочных данных.")
            return
        dec = Cipher(algorithms.AES(_K_ECB), modes.ECB()).decryptor()
        pt = dec.update(ct) + dec.finalize()
                                                                     
        try:
            pad = pt[-1]
            if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
                body = pt[:-pad]
            else:
                body = pt
        except IndexError:
            body = pt
        self.send("   Открытый текст: " + body.decode("utf-8", errors="replace"))

    def op_module_info(self):
        self.send(MODULE_INFO)

    def op_journal(self):
        self.send(JOURNAL)

    def op_auth(self):
        code = self.prompt("   Кодовая фраза оператора> ").strip()
        if code.encode("utf-8") == _PASSPHRASE:
            self.authorized = True
            self.send("   [ДОСТУП] Авторизация принята. Уровень: СТАРШИЙ ОПЕРАТОР.")
            self.send("   [ДОСТУП] Открыт архивный шифроканал (пункт 8) и депеша 0451.")
        else:
            self.send("   [ОТКАЗ] Кодовая фраза не распознана.")

    def op_archive_channel(self):
        if not self.authorized:
            self.send("   [ОТКАЗ] Архивный шифроканал доступен только старшему оператору.")
            return
        msg = self.prompt("   Текст для передачи в архив> ")
        data = msg.encode("utf-8")
        ct = ctr_crypt(_K_CTR, _IV_CTR, data)
        self.send("   [АРХИВ] Принято.")
        self.send("   Шифротекст (hex): " + ct.hex())

                                                                               

    def run(self):
        self.send(BANNER)
        while True:
            self.send(MENU)
            try:
                choice = self.prompt("   Выбор> ").strip()
            except EOFError:
                break
            if choice == "1":
                self.op_inventory()
            elif choice == "2":
                self.op_read()
            elif choice == "3":
                self.op_encrypt()
            elif choice == "4":
                self.op_decrypt()
            elif choice == "5":
                self.op_module_info()
            elif choice == "6":
                self.op_journal()
            elif choice == "7":
                self.op_auth()
            elif choice == "8":
                self.op_archive_channel()
            elif choice == "0":
                self.send("   [СИСТЕМА] Сеанс завершён. Канал закрыт.")
                break
            else:
                self.send("   [ОШИБКА] Неизвестная команда.")


class Handler(socketserver.StreamRequestHandler):
    timeout = 120

    def handle(self):
        try:
            Terminal(self.rfile, self.wfile).run()
        except (EOFError, ConnectionError, socket.timeout):
            pass
        except Exception:
            try:
                self.wfile.write("   [СБОЙ] Аварийное завершение сеанса.\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "1337"))
    with Server((host, port), Handler) as srv:
        print("[*] ШИФРАТОР слушает %s:%d" % (host, port), flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
