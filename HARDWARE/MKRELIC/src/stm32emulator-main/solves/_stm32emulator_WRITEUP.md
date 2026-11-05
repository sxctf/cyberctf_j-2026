# Writeup: STM32 Emulator / SRAM Recovery

## Кратко

Задание маскируется под работу с STM32-прошивкой, но флаг не выдается по UART. Прошивка оставляет диагностический crash trace в SRAM. Нужно снять дамп SRAM, найти заголовок `CRSH`, перейти к манифесту `SRM2`, отфильтровать настоящие фрагменты и декодировать их XOR-ключом `0x5a`.

Флаг:

```text
STM32LAB{sram_trace_manifest_recovery}
```

## Разведка

В `profiles/stm32_lab/config.yaml` описана виртуальная плата. Важная часть:

```yaml
- name: RAM
  start: 0x20000000
  size: 0x20000
```

Комментарии в конфиге прямо намекают на retained crash trace:

```text
CRSH header at 0x20000000, SRM2 manifest via the header pointer.
```

Прошивка общается по UART. Если отправить `probe`, она дает диагностические подсказки:

```text
DIAG: retained crash trace present
DIAG: header magic CRSH in SRAM bank 1
DIAG: follow header pointer to recovery manifest
DIAG: suggested read length 512
```

Команда `readflag` не помогает:

```text
DENIED: protected flag is not available over UART
HINT: inspect retained SRAM diagnostics
```

## Получение дампа

Через TUI/bridge достаточно выполнить прошивку, чтобы она скопировала retained trace в SRAM, а затем снять 512 байт:

```text
step 2100
dump 0x20000000 512
```

В начале дампа появляется заголовок:

```text
43 52 53 48 ... 40 00 00 00 ... 00 02 00 00 ...
```

`43 52 53 48` - это ASCII `CRSH`. Значение `0x40` в заголовке указывает на манифест по адресу:

```text
0x20000000 + 0x40 = 0x20000040
```

По этому адресу находится `SRM2`:

```text
53 52 4d 32
```

## Разбор SRM2

После заголовка `SRM2` идет таблица из 8 записей по 12 байт. Практически важные поля записи:

```text
u16 offset     # смещение фрагмента от начала CRSH-дампа
u8  length     # длина фрагмента
u8  order      # порядок в итоговой строке
u16 enabled    # 1 для настоящего фрагмента, 0 для decoy
u8  id
u8  kind       # 0x51 для настоящих фрагментов, 0x44 для decoy
u32 checksum
```

Настоящие записи имеют `enabled = 1` и `kind = 0x51`. Фрагменты дополнительно XOR-кодированы ключом `0x5a`.

Минимальный скрипт для декодирования прямо из `firmware.bin`:

```python
from pathlib import Path

fw = Path("profiles/stm32_lab/firmware.bin").read_bytes()

# Прошивка копирует 512 байт с offset 0x254 в SRAM по 0x20000000.
sram = fw[0x254:0x254 + 0x200]

assert sram[0:4] == b"CRSH"
manifest_off = int.from_bytes(sram[0x08:0x0c], "little")
assert sram[manifest_off:manifest_off + 4] == b"SRM2"

entries_off = manifest_off + 0x20
chunks = []

for i in range(8):
    entry = sram[entries_off + i * 12:entries_off + (i + 1) * 12]
    off = int.from_bytes(entry[0:2], "little")
    length = entry[2]
    order = entry[3]
    enabled = int.from_bytes(entry[4:6], "little")
    kind = entry[7]

    if enabled == 1 and kind == 0x51:
        raw = sram[off:off + length]
        decoded = bytes(b ^ 0x5a for b in raw).decode()
        chunks.append((order, decoded))

flag = "".join(part for _, part in sorted(chunks))
print(flag)
```

Вывод:

```text
STM32LAB{sram_trace_manifest_recovery}
```

## Почему это работает

Reset-handler прошивки копирует блок из flash offset `0x254` в SRAM `0x20000000`. UART-команды только подсказывают путь, но не раскрывают флаг. Реальные данные лежат в SRAM-дампе:

- `CRSH` подтверждает начало crash trace.
- Поле `0x40` ведет к манифесту `SRM2`.
- Таблица `SRM2` содержит как настоящие, так и ложные фрагменты.
- Настоящие фрагменты отмечены `kind = 0x51`, сортируются по `order` и XORятся с `0x5a`.

После сортировки фрагменты собираются так:

```text
STM32LAB{
sram_trace_
manifest_
recovery}
```
