# Novità

Ogni release pubblica come descrizione la sezione della propria versione.
Prima di creare una release aggiungi qui una sezione `## vX.Y.Z`.

## v1.3.0

- **Cartella con il nome del gioco**: i giochi vengono estratti in
  `Giochi\<Titolo>\CUSA00003` (es. `Giochi\Driveclub\CUSA00003`), così si
  riconoscono a colpo d'occhio. shadPS4 li trova comunque. Si può disattivare da
  *Impostazioni → Cartella con il nome del gioco* o con `--no-title-folder`.
- Se un gioco è già stato estratto altrove nella cartella giochi (anche nel
  vecchio formato `Giochi\CUSA00003`), aggiornamenti e patch vengono applicati
  lì invece di creare una seconda cartella.
- Gli interruttori nelle Impostazioni mostrano "Attivo"/"Disattivo" invece di
  "On"/"Off".

## v1.2.0

- Prima release pubblica.
- Versioni per **Linux** (AppImage) e **macOS** (Apple Silicon), oltre a Windows.
- **Controllo della versione installata**: avviso e conferma prima di riportare
  un gioco a una versione più vecchia; da riga di comando serve `--force`.
- Corretto l'errore "Immagine PFSC non trovata" con alcuni fPKG reali.
- Interfaccia in stile Windows 11 (Fluent) con tema chiaro e scuro.
