# SMO Android Port: versione per AYN Thor Max

Questo è un fork di [Deez-coder/SMO-android-port](https://github.com/Deez-coder/SMO-android-port) adattato all'**AYN Thor Max**
(Snapdragon 8 Gen 2 / Adreno 740, schermo principale 1920x1080 a 120 Hz, ventola attiva).

> Il repository non contiene il gioco, chiavi o firmware. L'APK si compila sul **tuo PC** partendo dal **tuo** dump e
> dalle **tue** `prod.keys`. Siccome contiene codice ricavato dal gioco, è solo per il tuo dispositivo: non condividerlo.

## Cosa cambia rispetto all'originale

| Cosa | Originale | Questo fork | Perché |
|---|---|---|---|
| Frame rate di default | 60 | **30 (velocità piena)** | Su uno Snapdragon 8 Gen 3 la modalità 60 fa 30-45 fps e il gioco rallenta. L'8 Gen 2 è più lento: 60 stabili non sono raggiungibili, 30 sì. |
| CPU boost | auto | **auto + guardia termica** | Il limite è la CPU: il boost tiene su i core medi (+4-5 fps nelle scene pesanti) solo quando i frame sono in ritardo, e si spegne da solo quando Android segnala calore "moderate". |
| Risoluzione | 1080p docked | 1080p docked (invariata) | È la risoluzione esatta dello schermo del Thor. Di più vuol dire supersampling: tanta GPU per un guadagno minimo. |
| Anti-aliasing / nitidezza | off / 0 | **FXAA + 25%** | Bordi puliti a costo quasi nullo, la nitidezza recupera il dettaglio. |
| Filtro anisotropico | gioco | **4x** | Texture più nitide in obliquo, costa pochissimo. |
| Cache shader/pipeline | salvata quando esci o vai in background | **anche ogni 90 s mentre giochi** (solo se è cresciuta) | Così le pipeline delle zone nuove non si perdono se l'app crasha o viene chiusa male, e lo scatto della prima visita non si ripete. `SMO_PCACHE_AUTOSAVE_S=0` in `config/env.txt` lo disattiva. |
| Ottimizzazione del compilatore | Cortex-A720 (8 Gen 3) | **Cortex-A715** (8 Gen 2) | Ottimizza l'ordine delle istruzioni per i core su cui girano i thread del gioco. Il set di istruzioni non cambia, quindi non c'è rischio di crash. |
| Compilazione | sul PC | **sul Thor**, dentro l'app | L'APK si scarica dal tuo GitHub (Releases) e non contiene niente del gioco. |
| Launcher | – | scheda **AYN Thor Max** nella pagina Graphics | Un pulsante riapplica le impostazioni consigliate, anche sopra un `graphics.ini` di una vecchia installazione. |

## Aspettative oneste

- **30 fps a velocità piena**: realistici quasi ovunque. Nelle scene più pesanti (es. la cascata di Cascade) l'originale
  scende a 24-27 su un S24 Ultra senza boost. Con boost + Turnip dovresti stare vicino ai 30.
- **60 fps stabili: no.** Il collo di bottiglia è la CPU (il thread del gioco e quello di rendering), non la GPU. Nessuna
  impostazione grafica lo risolve.
- Queste modifiche **non sono state provate su un Thor**: chi le ha scritte non aveva né il dispositivo né il gioco. Se
  qualcosa non va, esporta i log (vedi in fondo).

## Senza PC: compilazione direttamente sul Thor (consigliato)

L'APK di questo fork **non contiene codice del gioco**. Contiene un compilatore (clang + Python) e i sorgenti del
runtime. Il gioco lo compila il Thor stesso, partendo dal **tuo** ExeFS.

1. **Scarica l'APK** dall'ultima Release del repo: https://github.com/fooskow/SMO-android-port/releases/latest
   (il file `.apk` sotto "Assets"). Se avevi l'APK originale: esporta il salvataggio e disinstallalo, le firme sono diverse.
2. **Game → Import ExeFS folder…**: scegli la cartella dell'ExeFS di 1.0.0 (quella con `main`, `main.npdm`, `sdk`...).
3. **Game → Import RomFS folder…**: scegli la cartella della RomFS (5 GB: ci mette qualche minuto).
4. **Build the game**: compila in background, anche a schermo spento, con una notifica che mostra il passaggio in corso.
   Tienilo **in carica e al fresco**: è un'ora abbondante con la CPU piena. Si fa una volta sola. Se si interrompe,
   riparte dal passaggio dove era arrivato.
5. **Play**.

Con gli aggiornamenti dell'app si ricompila solo la parte cambiata (il runtime), quindi pochi minuti.
Se qualcosa va storto: **Build log** nella stessa scheda.

## In alternativa: compilazione sul PC

## 1. Preparare il PC (Windows, una volta sola)

Usa cartelle **senza spazi** nel percorso (es. `C:\smo`).

1. **Git for Windows** (include Git Bash): https://git-scm.com
2. **Python 3.11 o più recente**: https://python.org. Nell'installer spunta "Add python.exe to PATH".
3. **JDK 17** (Temurin): https://adoptium.net
4. **Android command-line tools**: https://developer.android.com/studio#command-tools. Estrai in
   `C:\smo\toolchain\sdk\cmdline-tools\latest\` (dentro ci deve essere `bin\sdkmanager.bat`), poi da Git Bash:
   ```bash
   export ANDROID_HOME=C:/smo/toolchain/sdk
   $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager.bat --licenses
   $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager.bat "build-tools;35.0.0" "platforms;android-35" "platform-tools" "ndk;28.2.13676358" "cmake;3.31.6"
   ```
5. Clona questo fork:
   ```bash
   cd /c/smo && git clone https://github.com/fooskow/smo-android-port && cd smo-android-port
   ```

## 2. Compilare l'APK (un comando)

Nella cartella del dump ci deve essere l'NSP di Super Mario Odyssey **1.0.0** (gioco base, senza update).

```bash
export ANDROID_HOME=C:/smo/toolchain/sdk
bash scripts/build_thor.sh --dump "C:/smo/dump" --keys "C:/smo/prod.keys"
```

Ci vogliono circa **2 ore** la prima volta: estrazione, un'ora di conversione in C, 40 minuti di compilazione. Se si
ferma per un errore, sistema e rilancia lo stesso comando: i passaggi già finiti vengono saltati.
Alla fine trovi `build/android/odyssey-0.1.0-thor.apk`.

**Conserva** `build/android/release.keystore` e `release.keystore.txt`: gli aggiornamenti futuri vanno firmati con la stessa chiave.

## 3. Installare sul Thor

1. Se avevi l'APK originale: **Game → Export save…** per salvare i progressi in uno .zip, poi **disinstallalo**.
   Le due app hanno firme diverse, quindi questa non può aggiornare l'altra.
2. Copia l'APK sul Thor e installalo. In alternativa: `bash scripts/build_thor.sh ... --install` con il Thor collegato
   via USB e il debug USB attivo.
3. Nell'app: **Import prod.keys…**, poi **Import from NSP / XCI…**, poi **Import save…** con il tuo .zip.

## 4. Driver Turnip (il guadagno più grande)

Su Adreno, il driver Mesa Turnip fa girare questo gioco nettamente più veloce di quello Qualcomm. Sull'S24 Ultra, nella
stessa scena: 33-35 fps contro 24-26.

1. Scarica un pacchetto Turnip AdrenoTools da https://github.com/K11MCH1/AdrenoToolsDrivers/releases (quello testato
   dall'autore è `Turnip_v26.0.0_R8.zip`). È codice che gira dentro il gioco: usa solo build di cui ti fidi.
2. Nell'app: **Advanced → Install a driver package (.zip)…**
3. Il driver di default è già "custom". Se dà problemi, **Use → Phone's own**.

## 5. Impostazioni del Thor

- **Menu AYN → modalità prestazioni al massimo** e **ventola su una curva aggressiva**: il CPU boost scalda, la ventola deve stargli dietro.
- Lancia il gioco sullo **schermo superiore** (tieni premuta l'icona → Screen Launch → Top Screen).
- Usa i **controlli fisici**: i comandi touch si nascondono da soli e la GPU resta più fresca.
- **Primo avvio**: 2-3 minuti di "Preparing graphics". Poi esci dal gioco col tasto Home/Exit: la cache viene salvata e
  dal secondo avvio il titolo arriva in circa 20 secondi.

## Problemi?

**Advanced → Export logs** crea uno .zip con log, impostazioni e modello. Ogni 10 secondi c'è una riga `perf:` con fps,
1% low, frequenze CPU e stato termico: serve per capire cosa succede sul Thor.
