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

## Зависимости

- **Python 3.10+**
- **PyQt6**, **PyQt6-WebEngine**, **PyQt6-Multimedia**, **PyQt6-WebChannel**
- **slixmpp**, **qasync**, **defusedxml**, **aiodns**
- Опционально, для звонков: **aiortc** (`pip install stanza-im[calls]`)
- Опционально, для проверки орфографии: **pyenchant**
  (`pip install stanza-im[spellcheck]`) и системные словари `hunspell-*`
  (например, `hunspell-ru`, `hunspell-en-us`) с `libenchant-2-2`
- Системные библиотеки Qt/веб-движка: `libglib-2.0`, `libGL`, `libgl1`,
  `libx11`, `libfontconfig`

В Debian 13 нужные для работы пакеты можно установить следующей командой:

```
sudo apt-get install python3-slixmpp python3-pyqt6 python3-pyqt6.qtwebengine python3-defusedxml python3-qasync python3-aiodns python3-aiortc python3-pyqt6.qtmultimedia fonts-noto-color-emoji
```

Для работы шифрования OMEMO дополнительно нужны такие пакеты:

```
sudo apt-get install python3-omemo python3-oldmemo python3-twomemo python3-omemo-dr python3-slixmpp-omemo python3-xmlschema
```

Для проверки орфографии нужны `libenchant-2-2` и словари нужных языков,
например:

```
sudo apt-get install libenchant-2-2 hunspell-ru hunspell-en-us
```

## Документация проекта

Сборка/архитектура — [AGENTS.md](AGENTS.md).