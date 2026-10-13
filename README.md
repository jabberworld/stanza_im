# Stanza IM

Лёгкий и быстрый, гибко настраиваемый и функциональный десктопный **XMPP/Jabber**-клиент для Linux с поддержкой современных стандартов — основан на идеях Jabbim, Psi и немного из Gajim.
Написан на **Python 3.10+** с использованием PyQt6 и slixmpp.

## Ключевые возможности

- текстовые чаты
- аудио- и видеозвонки
- совместное рисование
- файлообмен
- шифрование переписки

...и многое другое, с чем можно ознакомиться в [FEATURES.md](FEATURES.md)


Полный список поддерживаемых расширений — в [XEPs.md](XEPs.md),
детальная спецификация внутреннего устройства — в [SPEC.md](SPEC.md).

Проверка соответствия современным стандартам - в [CHECKLIST.md](CHECKLIST.md).

## Запуск

```bash
python main.py
```

## Зависимости

- **Python 3.10+**
- **PyQt6**, **PyQt6-WebEngine**, **PyQt6-Multimedia**, **PyQt6-WebChannel**
- **slixmpp**, **qasync**, **defusedxml**, **aiodns**
- Опционально, для звонков: **aiortc** (`pip install stanza-im[calls]`)
- Системные библиотеки Qt/веб-движка: `libglib-2.0`, `libGL`, `libgl1`,
  `libx11`, `libfontconfig`

В Debian 13 нужные для работы пакеты можно установить следующей командой:

```
sudo apt-get install python3-slixmpp python3-pyqt6 python3-pyqt6.qtwebengine python3-defusedxml python3-qasync python3-aiodns python3-aiortc python3-pyqt6.qtmultimedia fonts-noto-color-emoji
```

## Документация проекта

Сборка/архитектура — [AGENTS.md](AGENTS.md).