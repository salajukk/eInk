# Automaattinen GitHub-päivitys ja jatkuva käyttö

Perheen näyttö julkaistaan Raspberry Pi 5 -palvelimella kodin sisäverkkoon. `dashboard_supervisor.py` käynnistää `web_dashboard.py`-palvelimen, valvoo prosessia ja hakee koodipäivitykset GitHubista.

**Aktiivinen kehityshaara on `main`.** `family-dashboard-v1`-haaran sisältö yhdistettiin siihen 15.11.2026. Vanha haara on säilytetty, jotta kotona jo käynnissä oleva Raspberry Pi -asennus ei lakkaa toimimasta ennen paikallista haaranvaihtoa.

## Toimintaperiaate

Valvoja käynnistää web-palvelimen, tarkistaa GitHubin `origin/main`-haaran oletuksena 60 sekunnin välein, tekee vain fast-forward-tyyppisiä päivityksiä ja käynnistää web-palvelimen uudelleen, jos uusia muutoksia tuli. Web-palvelin päivittää näkymän 30 sekunnin välein. Jos palvelinprosessi kaatuu, valvoja käynnistää sen uudelleen.

Valvoja ei vaihda Git-haaraa itsestään. Käynnistettäessä se tarkistaa, että paikallinen haara ja `--branch`-valinta vastaavat toisiaan. Uudessa `main`-versiossa valinnan oletusarvo on `main`.

## Kotipalvelimen asennus

Käytössä oleva laite on Raspberry Pi 5 (2 Gt) ja Raspberry Pi OS Lite 64-bit. Sovellus on sijoitettu hakemistoon `~/eInk`, käytössä on projektin `venv`-virtuaaliympäristö ja paikallinen, versionhallinnasta pois jätetty `config.yaml`. Laitteen verkko-osoite pidetään vakaana reitittimen DHCP-varauksella. Tabletin selaimelle käytetään Raspberry Pin sisäverkon IP-osoitetta portissa 8080; `.local`-nimeen ei kannata luottaa pysyvänä osoitteena.

Uusi asennus:

~~~bash
git clone https://github.com/salajukk/eInk.git
cd eInk
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
cp config.example.yaml config.yaml
# täydennä config.yaml paikallisesti
venv/bin/python dashboard_supervisor.py
~~~

Palvelu voidaan käynnistää automaattisesti `systemd`:llä esimerkiksi tällä yksiköllä (`/etc/systemd/system/family-dashboard.service`):

~~~ini
[Unit]
Description=Family Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_PI_USER
WorkingDirectory=/home/YOUR_PI_USER/eInk
ExecStart=/home/YOUR_PI_USER/eInk/venv/bin/python /home/YOUR_PI_USER/eInk/dashboard_supervisor.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
~~~

Korvaa `YOUR_PI_USER` oikealla Raspberry Pin käyttäjällä ja ota palvelu käyttöön:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now family-dashboard.service
systemctl status family-dashboard.service --no-pager
~~~

Päänäkymä: `http://<raspberry-pin-lähiverkon-ip>:8080`. Palvelun terveystesti: `/health`.

## Jo käytössä olevan Raspberry Pi:n siirtäminen vanhasta haarasta

**GitHubin merge ei muuta Raspberry Pin Git-haaraa.** Jos palvelimen paikallinen haara on edelleen `family-dashboard-v1`, se seuraa edelleen vanhaa haaraa ja näyttö toimii normaalisti, mutta se ei saa uusia `main`-haaran päivityksiä.

Siirto tehdään kerran SSH-yhteydellä. Tarkista mahdolliset paikalliset muutokset ensin; älä ylikirjoita niitä:

~~~bash
cd ~/eInk
git status --short
sudo systemctl stop family-dashboard.service
git fetch origin main
git switch main
git pull --ff-only origin main
sudo systemctl start family-dashboard.service
systemctl status family-dashboard.service --no-pager
~~~

Jos `git status --short` näyttää versionhallittujen tiedostojen muutoksia tai `git switch main` ilmoittaa ristiriidasta, korjaa tilanne ennen jatkamista; älä käytä `--force`- tai `reset --hard` -komentoja. Omat tunnukset ja salaiset osoitteet säilyvät paikallisessa, gitignore-säännöissä olevassa `config.yaml`-tiedostossa. Tarkista palvelun mahdolliset erilliset käynnistysparametrit komennolla `systemctl cat family-dashboard.service`: jos palvelu käyttää `--branch family-dashboard-v1`, muuta parametri `--branch main` ja lataa palvelumäärittely uudelleen.

Mikäli palvelu ei käynnisty, tarkista lokit:

~~~bash
journalctl -u family-dashboard.service -n 100 --no-pager
~~~

## Päivityksen turvarajat

- Automaattinen päivitys onnistuu vain, jos Git-työpuun versionhallittu osa on puhdas ja etähaaran muutos voidaan ottaa käyttöön fast-forwardina.
- Paikallisia versionhallittuja muutoksia ei ylikirjoiteta, eikä valvoja vaihda haaraa.
- `config.yaml`, salaisuudet ja `cache/` pysyvät paikallisina eikä niitä viedä GitHubiin.
- Valvoja **ei asenna Python-riippuvuuksia**. Jos `requirements*.txt` muuttuu, tee virtuaaliympäristön `pip install -r requirements.txt` erikseen.
- `dashboard_supervisor.py` pyrkii lataamaan itsensä uudelleen, jos sen oma tiedosto muuttui päivityksessä.

## Käyttö Windows-kehityskoneella

Käytä projektin `main`-haaraa. Voit käynnistää valvojan PowerShellistä:

~~~powershell
.\venv\Scripts\python.exe dashboard_supervisor.py
~~~

Tavallinen web-palvelin voidaan testata ilman valvojaa myös komennolla `python web_dashboard.py`. Windowsia ei tarvita Raspberry Pi:n jatkuvaan käyttöön.

**Tietoturva:** näkymä on tarkoitettu vain luotettuun kotiverkkoon. Älä avaa palvelimen porttia 8080 suoraan internetiin, sillä sisältö voi paljastaa perheen kalenteri- ja koulutietoja.

Katso myös [README.md](README.md), [SYSTEM_HEALTH.md](SYSTEM_HEALTH.md) ja [TABLET_MONTH_CALENDAR.md](TABLET_MONTH_CALENDAR.md).
