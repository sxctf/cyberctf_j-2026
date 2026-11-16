SWITCH_MANUAL = """
ЛК-2408 Руководство (фрагменты — полные PDF у организатора)
  use sw
  <password из PDF, рукописная пометка>

  port <p> pvid <vlan>       — назначить PVID
  port <p> up|down           — включить/выключить
  port <p> guard clear       — снять GUARD  (не up! — рукописная пометка)
  seg <id> member <p> tag    — добавить порт в сегмент как tag
  filter <name> rule <n> del — удалить правило
  cfg begin / apply / confirm / save

ВНИМАНИЕ (рукописное): PVID и untag — НЕ одно и то же.
Правила фильтра проверяются по УБЫВАНИЮ номера.
"""

FW_MANUAL = """
ЛК-2408-FW Руководство (фрагменты)
  use fw
  <password из PDF, рукописная пометка>

  zone <name> member <eth>   — добавить интерфейс в зону
  policy <name> rule <n> <action> <proto> <src> -> <dst> [dport <n>]
  policy <name> apply        — применить политику в dataplane
  cfg apply / confirm / save

ВНИМАНИЕ (рукописное): policy без apply — не работает.
"""