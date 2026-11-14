# Perheen näyttö

**Perheen näyttö** on kotona käytössä oleva, selaimella avattava perheen yhteinen tietonäyttö. Raspberry Pi 5 julkaisee näkymän kodin sisäverkkoon: käyttämättömäksi jäänyt Android-tabletti näyttää sitä kiosk-tilassa ja sama osoite toimii myös perheen puhelimissa ja tietokoneissa, kun ne ovat kodin Wi-Fi-verkossa.

**Toteutuksen tila:** käytössä kotiverkossa. **E-ink-näyttöä ei enää tavoitella eikä tarvita.** Repositorion nimi `eInk` sekä osa tiedostoista ja asetusten nimistä ovat aiemman laitteistosuunnitelman perintöä.

> **Tärkeää GitHub-haaroista:** nykyinen sovellus sijaitsee haarassa **`family-dashboard-v1`**. Repositorion oletushaara `main` sisältää vanhan e-ink-painotteisen version, eikä sen koodi vastaa tätä kotiverkon web-sovellusta.

## Näin järjestelmä toimii

~~~text
                    KODIN WIFI / LÄHIVERKKO

  Tietolähteet
  (kalenterit, sää, Wilma, HSL, muistutukset)
                 |
                 v
  Raspberry Pi 5 (aina päällä)
    Python-datamoduulit -> render_family_13in3.py
    -> output/dashboard.png -> web_dashboard.py :8080
                 |
                 +--> Android-tabletti, kiosk-tila
                 +--> perheen puhelimet ja tietokoneet
~~~

- **Palvelin:** Raspberry Pi 5 (2 Gt), Raspberry Pi OS Lite 64-bit. Laite toimii ilman näyttöä, SSH-istuntoa tai jatkuvasti päällä olevaa muuta tietokonetta.
- **Julkaisu:** Pythonin HTTP-palvelin `web_dashboard.py` kuuntelee oletuksena osoitteessa `0.0.0.0:8080`, jotta näkymä on käytettävissä kodin lähiverkossa.
- **Pysyvä osoite:** reitittimeen on tehty Raspberry Pille DHCP-varaus. Tabletilla käytetään varattua lähiverkon IP-osoitetta, koska `.local`-nimen toiminta ei ollut luotettavaa.
- **Yhteinen näyttö:** vanha Android-tabletti on jätetty näyttämään verkkosivua kiosk-tilassa. Erillistä e-paperia, GPIO-näyttöä tai tablettiin asennettavaa Python-sovellusta ei tarvita.
- **Automaattinen käynnistys:** `family-dashboard.service` käynnistää `dashboard_supervisor.py`-prosessin Raspberry Pi -palvelimen käynnistyessä. Palvelimen toiminta uudelleenkäynnistyksen jälkeen on varmistettu kotikäytössä.

## Käyttö

Avaa millä tahansa kodin samaan lähiverkkoon liitetyllä laitteella:

~~~text
http://<raspberry-pin-lähiverkon-ip>:8080
~~~

Raspberry Pi -palvelimella voit tarkistaa näkymän myös osoitteesta `http://localhost:8080`. Kodin ulkopuolelle ei ole tarkoitus avata julkista yhteyttä.

### Neljä selainnäkymää

1. **Perheen näyttö (etusivu)** – yhdellä silmäyksellä luettava päivätilanne. Pääasiallinen sisältö piirtyy 960 × 680 pikselin PNG-kuvaksi ja selaimessa kuva skaalautuu näyttöön.
2. **Kuukausikalenteri** – pyyhkäise etusivulta **vasemmalle**. Näyttää kalenterien tapahtumat kuukausittain, voidaan vierittää pystysuunnassa ja kuukautta voi vaihtaa nuolilla. Pyyhkäise oikealle palataksesi etusivulle.
3. **Raspberry Pi -järjestelmän tila** – pyyhkäise etusivulta **oikealle**. Sisältää lämpötilan, suorituskyvyn, muistin, levytilan, palvelun ja yhteyksien tilan. Pyyhkäise vasemmalle palataksesi.
4. **Koulusta muistettavaa** – avaa kuukausikalenterista pyyhkäisemällä **vasemmalle** tai painamalla koulumuistutusten linkkiä; myös suora reitti `/school`. Sisältää lasten koulutehtäviä, kokeita, merkintöjä ja Wilma-viesteistä poimittuja muistutuksia.

Päänäkymässä on lisäksi linkki koulumuistutuksiin. Kiosk-tilan tarkat asetukset riippuvat käytetystä Android-tabletista ja kiosk-selaimesta; sovellus itsessään on tavallinen verkkosivu.

### Tietosisältö

Toteutus hyödyntää seuraavia moduuleja. Käytössä olevat ominaisuudet määritellään paikallisen `config.yaml`-tiedoston `features`-osiossa.

| Sisältö | Lähde tai toiminta |
| --- | --- |
| Kello, päivä ja sää | Palvelimen aika sekä Open-Meteo |
| Perheen kalenterit | Yksityiset Google Calendar / iCal -syötteet |
| Lasten koulukalenterit | Wilman yksityiset iCal-syötteet |
| Koulumuistutukset | Wilma-viestit, läksyt, kokeet ja merkinnät; paikallinen tilatieto ja tarvittaessa AI-analyysi |
| Joukkoliikenne | HSL / Digitransit, jos API-avain ja pysäkit on määritelty |
| Muistettavaa | Paikallisessa konfiguraatiossa määritellyt tehtävät |
| Järjestelmän tila | Raspberry Pi -palvelimen paikalliset mittaukset |

Koulumuistutusten erillinen ajo käyttää `wilma_nightly.py`-skriptiä ja tallentaa yksityisen tuloksen paikalliseen välimuistiin. Nykyisessä asennuksessa se ajetaan päivän aikana klo 12, 13, 14 ja 15 (Europe/Helsinki). Selainnäkymän avaaminen ei itsessään käynnistä Wilman tai AI:n hakua.

## Käynnistäminen kehityskoneella tai uudella Raspberry Pi:llä

Ohjeet koskevat **`family-dashboard-v1`-haaraa**, eivät vanhaa `main`-haaraa.

~~~bash
git clone --branch family-dashboard-v1 https://github.com/salajukk/eInk.git
cd eInk
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
cp config.example.yaml config.yaml
~~~

Muokkaa `config.yaml`-tiedostoon omat kalenterit, tunnukset, sijainti, mahdolliset HSL-tiedot sekä `features`-valinnat. Päänäkymän nykyiset kuvakoko- ja asetteluasetukset ovat:

~~~yaml
display:
  width: 960
  height: 680
  layout: family_13in3
~~~

Asetuksen nimi `family_13in3` on historiallinen; se valitsee käytössä olevan kuvapohjaisen perhenäkymän **eikä tarkoita, että e-paperinäyttö olisi käytössä**. Myös mallinimi `waveshare_13in3k` voi esiintyä vanhoissa konfiguraatioissa, mutta `web_dashboard.py` ei ohjaa näyttölaitteistoa.

Käynnistä lähiverkon verkkopalvelu:

~~~bash
venv/bin/python web_dashboard.py
~~~

Oletukset: HTTP-portti **8080**, kuvan renderöinti **30 sekunnin välein**, kuvan automaattinen päivitys selaimessa. Tavallista sää- ja kalenterivälimuistia rajataan web-käytössä enintään viiteen minuuttiin ja HSL-välimuistia enintään yhteen minuuttiin; vanhentuneet lähdöt poistetaan näytöstä myös renderöintien yhteydessä.

Esimerkiksi portin ja renderöintivälin voi vaihtaa näin:

~~~bash
venv/bin/python web_dashboard.py --host 0.0.0.0 --port 8080 --refresh-seconds 30 --config config.yaml
~~~

Windowsilla käytä virtuaaliympäristön Pythonia `venv\Scripts\python.exe`. Verkkopalvelin toimii ilman fyysistä e-ink-laitetta.

## Raspberry Pi:n jatkuva käyttö ja automaattiset GitHub-päivitykset

Kotona palvelin ajetaan `dashboard_supervisor.py`-prosessin kautta. Se käynnistää web-palvelimen, valvoo sitä ja tarkistaa **`origin/family-dashboard-v1`**-haaran päivitykset oletuksena **60 sekunnin välein**. Uudempi koodi otetaan käyttöön vain turvallisella fast-forward-päivityksellä; paikallisia muokattuja versionhallittuja tiedostoja ei ylikirjoiteta. Palvelu käynnistetään `systemd`:llä.

Käynnistyksen testaus:

~~~bash
cd ~/eInk
venv/bin/python dashboard_supervisor.py
~~~

Nykyisen palvelun tilan ja lokien tarkistus:

~~~bash
systemctl status family-dashboard.service
journalctl -u family-dashboard.service -n 100 --no-pager
~~~

Katso palvelun luonti ja käyttöönotto tiedostosta [AUTO_UPDATE.md](AUTO_UPDATE.md). **Huom:** automaattinen Git-päivitys ei asenna uusia Python-riippuvuuksia; jos `requirements.txt` muuttuu, riippuvuudet on päivitettävä palvelimella erikseen.

## Tarkistus ja ylläpito

| Osoite / komento | Käyttötarkoitus |
| --- | --- |
| `/` | Perheen pääsivu |
| `/dashboard.png` | Viimeksi renderöity pääkuva |
| `/health` | Web-palvelun terveystarkistus |
| `/system` ja `/system-health.json` | Raspberry Pin tila |
| `/calendar-month.json?year=2026&month=11` | Kuukausikalenterin data |
| `/school` ja `/school-reminders.json` | Koulunäkymä ja tallennettu muistutusaineisto |

Yksittäisten tietolähteiden vianetsintää varten:

~~~bash
venv/bin/python main.py --only weather --no-cache
venv/bin/python main.py --only calendar --no-cache
venv/bin/python main.py --only school --no-cache
venv/bin/python main.py --only hsl --no-cache
venv/bin/python -m unittest tests.test_calendar_month tests.test_swipe_navigation tests.test_system_health -v
~~~

Osa testeistä ja tietolähdekomennoista edellyttää vastaavan ominaisuuden asetuksia ja tunnuksia.

## Tietosuoja ja verkkoturvallisuus

**Verkkosovellus on tarkoitettu vain luotettuun kotiverkkoon.** Nykyinen HTTP-palvelin ei toteuta käyttäjäkohtaista kirjautumista. Saman lähiverkon käyttäjät voivat nähdä perheen kalenteri- ja koulutietoja. Älä tee reitittimeen porttiohjausta palvelulle äläkä julkaise sitä suoraan internetiin.

- `config.yaml` sisältää yksityisiä iCal-osoitteita, tunnuksia ja API-avaimia; se on gitignore-säännöissä eikä kuulu GitHubiin.
- `cache/` sisältää paikallista, mahdollisesti arkaluonteista perhedataa; sitä ei pidä jakaa tai viedä versionhallintaan.
- AI-pohjainen Wilma-viestien analyysi voi käyttää erikseen määriteltyä palvelua tai paikallisesti käynnistettyä Codex-ajoa. Tarkista alkuperäinen Wilma-viesti, jos muistutus on epäselvä.
- Kiosk-tabletin on oltava luotetussa kotiverkossa. Vältä turhaa henkilökohtaisten tietojen näyttämistä vierasverkkoon liitetyille laitteille.

## Keskeiset tiedostot

~~~text
web_dashboard.py           # HTTP-palvelin ja selaimen neljä näkymää
dashboard_supervisor.py    # web-prosessi ja GitHub-päivitysvalvonta
main.py                    # tietomoduulien ajaminen ja renderöinnin orkestrointi
render_family_13in3.py     # nykyisen päänäkymän 960x680 PNG-renderöinti
data/                      # sää, kalenterit, koulu, HSL, muistutukset jne.
integrations/              # Wilma-tiedonhaku
analysis/                  # koulumuistutusten analyysi
school_summary_page.py     # koulumuistutusten web-data
system_health.py           # Raspberry Pi:n terveystiedot
system_health_page.py      # terveystietojen selainkäyttöliittymä
wilma_nightly.py           # ajastettu Wilma-päivitys
config.example.yaml        # asetusten mallipohja; oikea config.yaml vain paikallisesti
tests/                     # yksikkö- ja käyttöliittymätestit
~~~

Lisätietoja: [AUTO_UPDATE.md](AUTO_UPDATE.md) (käyttöönotto ja automaattinen päivitys), [TABLET_MONTH_CALENDAR.md](TABLET_MONTH_CALENDAR.md) (kalenteri), [SYSTEM_HEALTH.md](SYSTEM_HEALTH.md) (valvonta) sekä [WILMA_REMINDERS.md](WILMA_REMINDERS.md) (koulumuistutukset). Näissä ja vanhoissa `FAMILY_DASHBOARD.md`- ja `PROJECT_CONTEXT.md`-muistiinpanoissa voi yhä olla e-paperia koskevia historiallisia suunnitelmia.

**Projektin nykyinen suunta:** ylläpidetään toimivaa, kodin Wi-Fi-verkossa käytettävää Raspberry Pi + selain + kiosk-tabletti -ratkaisua. Vanhoja `display/epaper*.py`-tiedostoja ei ole vielä poistettu, mutta ne eivät ole osa käytössä olevaa ratkaisua eivätkä enää sen kehitystavoite.
