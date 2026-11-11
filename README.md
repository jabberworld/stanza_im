# Stanza IM

Лёгкий и быстрый, гибко настраиваемый и функциональный десктопный **XMPP/Jabber**-клиент для Linux с поддержкой современных стандартов — основан на идеях Jabbim, Psi и немного из Gajim.
Написан на **Python 3.10+** с использованием PyQt6 и slixmpp.

## Ключевые возможности

- текстовые чаты
- аудио- и видеозвонки
- совместное рисование
- файлообмен
- шифрование переписки и файлов

...и многое другое, с чем можно ознакомиться в [FEATURES.md](FEATURES.md)


Полный список поддерживаемых расширений — в [XEPs.md](XEPs.md),
детальная спецификация внутреннего устройства — в [SPEC.md](SPEC.md).

Проверка соответствия современным стандартам - в [CHECKLIST.md](CHECKLIST.md).

## Запуск

```bash
python main.py
```

## Интеграция с рабочим столом

Установить ярлык и обработчик ссылок `xmpp:` для текущего пользователя:

```bash
python3 tools/install_desktop.py
xdg-mime query default x-scheme-handler/xmpp
```

Установщик кладёт `.desktop`-файл и иконку в `$XDG_DATA_HOME`, не требует
root и сам регистрирует `x-scheme-handler/xmpp`. Если Stanza IM уже запущен,
новая `xmpp:`-ссылка пересылается в существующее окно через локальный сокет.

Удалить ярлык и иконку:

```bash
python3 tools/install_desktop.py --uninstall
```

## Зависимости

- **Python 3.10+**
- **PyQt6**, **PyQt6-WebEngine**, **PyQt6-Multimedia**, **PyQt6-WebChannel**
- **slixmpp**, **qasync**, **defusedxml**, **aiodns**
- Опционально, для звонков: **aiortc** (`pip install stanza-im[calls]`)
- Опционально, для проверки орфографии: системный **python3-enchant** или
  pip-пакет **pyenchant** (`pip install stanza-im[spellcheck]`) плюс
  системные словари `hunspell-*` (например, `hunspell-ru`, `hunspell-en-us`)
- Системные библиотеки Qt/веб-движка: `libglib-2.0`, `libGL`, `libgl1`,
  `libx11`, `libfontconfig`

В Debian 13 нужные для работы пакеты можно установить следующей командой:

```
sudo apt-get install python3-slixmpp python3-pyqt6 python3-pyqt6.qtwebengine python3-defusedxml python3-qasync python3-aiodns python3-aiortc python3-pyqt6.qtmultimedia python3-enchant fonts-noto-color-emoji
```

Для работы шифрования OMEMO дополнительно нужны такие пакеты:

```
sudo apt-get install python3-omemo python3-oldmemo python3-twomemo python3-omemo-dr python3-slixmpp-omemo python3-xmlschema
```

Для проверки орфографии на Debian нужен `python3-enchant` (он сам подтягивает
`libenchant-2-2`) и словари нужных языков, например:

```
sudo apt-get install python3-enchant hunspell-ru hunspell-en-us
```

Для venv или других систем можно поставить `pip install stanza-im[spellcheck]`
и отдельно `libenchant-2-2`/`hunspell-*` средствами ОС.

## Документация проекта

Сборка/архитектура — [AGENTS.md](AGENTS.md).