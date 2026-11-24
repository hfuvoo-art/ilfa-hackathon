# data/ — локальные данные (в git НЕ попадают)

```
data/
  raw/anonymized/*.xls   ← распакованный архив anonymized.rar
  ilfa.db                ← база, которую строит скрипт из etl/
```

Распаковка (RAR5):
- macOS: `brew install libarchive` затем `bsdtar -xf anonymized.rar -C data/raw/`, или приложение The Unarchiver / Keka.
- Windows: 7-Zip или WinRAR, распаковать в `data\raw\`.
- Linux: `sudo apt install libarchive-tools && bsdtar -xf anonymized.rar -C data/raw/`.

После распаковки должно быть 8 652 файла `Визит № NNNNNN.xls`.
