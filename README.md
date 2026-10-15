# PKG Free

Programma per Windows che estrae i file **PKG PS4** in una cartella pronta per
l'emulatore [shadPS4](https://github.com/shadps4-emu/shadPS4), unendo
**gioco base + aggiornamenti (patch)** in un'unica cartella aggiornata e
sistemando i **DLC** nella struttura che shadPS4 si aspetta.

> Sono supportati solo i PKG **"fake" (fPKG)**: backup dei propri giochi e
> homebrew firmati con le chiavi di debug pubbliche. I PKG retail scaricati dal
> PlayStation Store sono cifrati con chiavi della console e **non** possono
> essere estratti. Usa il programma solo con contenuti di cui possiedi i diritti.

![Pagina Estrai, tema chiaro](docs/estrai-chiaro.png)

## Download

Ogni push compila automaticamente gli eseguibili Windows con GitHub Actions
(scheda **Actions** → ultima esecuzione di *Build Windows* → artefatto
`PkgFree-windows`). Creando un tag `v*` (es. `v1.0.0`) viene pubblicata anche
una release con lo zip.

Contenuto:

- `PkgFree.exe`: interfaccia grafica (~60–80 MB perché include Qt)
- `pkgfree-cli.exe`: versione da riga di comando

## Uso (interfaccia grafica)

L'interfaccia segue lo stile **Fluent** di Windows 11 (menu laterale, schede,
sfondo Mica) e supporta il **tema chiaro e scuro**.

1. Avvia `PkgFree.exe`.
2. Nella pagina **Estrai** trascina i file `.pkg` (o usa **Aggiungi PKG…** /
   **Aggiungi cartella…**): gioco base, aggiornamenti e DLC, in qualsiasi
   ordine. Il tipo viene riconosciuto dal `param.sfo` e i PKG vengono
   **raggruppati per gioco**: ogni scheda mostra icona, versione finale e
   l'**ordine di applicazione** (base → aggiornamenti per `APP_VER` → DLC).
   Eventuali problemi (gioco base mancante, patch delta) compaiono come avvisi
   nella scheda.
3. In basso scegli la **cartella giochi** (la cartella DLC si imposta in
   **Impostazioni**; se vuota si usa `<cartella giochi>\addcont`).
4. Premi **Estrai tutto**: si apre la pagina **Avanzamento** con percentuale,
   velocità, tempo rimanente e lo stato di ogni PKG. Il pulsante **Annulla**
   interrompe l'operazione. I messaggi dettagliati sono nella pagina
   **Registro**.

**Tema chiaro/scuro**: pulsante **Cambia tema** nel menu laterale (in basso),
oppure **Impostazioni → Aspetto → Tema** con le opzioni *Chiaro*, *Scuro* e
*Usa impostazione di sistema* (predefinita). La scelta viene ricordata.

| Avanzamento (scuro) | Completato (scuro) | Impostazioni (chiaro) |
|---|---|---|
| ![](docs/avanzamento-scuro.png) | ![](docs/completato-scuro.png) | ![](docs/impostazioni-chiaro.png) |

Risultato:

```
<cartella giochi>\CUSA12345\                        gioco + tutti gli aggiornamenti
<cartella DLC>\CUSA12345\<ENTITLEMENT_LABEL>\       un DLC per cartella
```

In shadPS4:

- aggiungi la *cartella giochi* tra le cartelle dei giochi;
- imposta la *cartella DLC* come cartella dei contenuti aggiuntivi
  (`addon install dir`, oppure `shadPS4.exe --set-addon-folder "<cartella DLC>"`).
  In alternativa scegli direttamente come cartella DLC quella predefinita di
  shadPS4 (`user\addcont`).

Opzione **Impostazioni → Unisci gli aggiornamenti al gioco** (attiva di
default): se la disattivi, le patch vengono estratte in `CUSA12345-UPDATE`
accanto al gioco, formato che shadPS4 riconosce e sovrappone al gioco base
all'avvio. Le impostazioni sono salvate in `%APPDATA%\PkgFree\config.json`.

## Uso (riga di comando)

```bat
pkgfree-cli info gioco.pkg patch.pkg --files
pkgfree-cli install gioco.pkg patch_1.01.pkg patch_1.05.pkg dlc1.pkg -o D:\PS4\Giochi
pkgfree-cli install patch.pkg -o D:\PS4\Giochi --separate-update
pkgfree-cli install dlc.pkg -o D:\PS4\Giochi --addons C:\shadPS4\user\addcont
```

## Note e limiti

- Le patch **delta** (incrementali) contengono solo le differenze e non
  possono essere unite: viene mostrato un avviso. Le patch fPKG comuni sono
  complete/cumulative e funzionano.
- I DLC che sono solo "chiavi di sblocco" (senza dati) producono una cartella
  con il solo `sce_sys\param.sfo`: è corretto, shadPS4 li riconosce così.
- I file esistenti nella destinazione vengono sovrascritti.
- Velocità indicativa: decine di MB/s (decifratura AES-XTS + decompressione).

## Compilare da sorgente

Serve Python 3.10 o successivo (la GUI usa PySide6 e PySide6-Fluent-Widgets).

```bat
build.bat
```

oppure manualmente:

```bat
pip install -r requirements.txt pyinstaller
set QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests
set QT_QPA_PLATFORM=
pyinstaller --onefile --windowed --name PkgFree --exclude-module tkinter pkgfree_gui.py
pyinstaller --onefile --console --name pkgfree-cli --exclude-module PySide6 --exclude-module qfluentwidgets pkgfree_cli.py
```

Senza compilare: `python -m pkgfree` (GUI) oppure `python -m pkgfree install ...`.

## Struttura del codice

| File | Contenuto |
|---|---|
| `pkgfree/pkg.py` | lettura PKG, decifratura PFS (AES-XTS), decompressione PFSC, estrazione |
| `pkgfree/crypto.py` | RSA / AES-CBC / HMAC / XTS |
| `pkgfree/keys.py` | chiavi RSA pubbliche per fPKG |
| `pkgfree/installer.py` | unione gioco + patch + DLC |
| `pkgfree/gui/` | interfaccia Fluent: `extract_page.py` (schede per gioco), `progress_page.py` (avanzamento + thread di estrazione), `settings_page.py` (impostazioni, registro), `window.py`, `config.py` |
| `pkgfree/cli.py` | riga di comando |
| `tests/` | test con PKG sintetici generati al volo, più uno smoke test della GUI |

## Licenza

GPL-3.0-or-later (richiesta da PySide6-Fluent-Widgets, GPLv3). Il formato e le
chiavi derivano dall'estrattore PKG (GPL-2.0-or-later) storicamente incluso in
shadPS4 e da LibOrbisPkg.
