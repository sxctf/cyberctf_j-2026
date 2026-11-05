# Temperature Converter

## Описание
Навык для конвертации температуры между шкалами:
- **Celsius** (°C)
- **Fahrenheit** (°F)
- **Kelvin** (K)

## Использование
Вызовите функцию `convert_temperature` с параметрами:
- `value` — числовое значение температуры
- `from_unit` — исходная единица (`C`, `F`, `K`)
- `to_unit` — целевая единица (`C`, `F`, `K`)

## Пример
```python
from converter import convert_temperature

result = convert_temperature(100, "C", "F")
print(result)  # 212.0
```
