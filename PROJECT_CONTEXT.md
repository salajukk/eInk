# Perheen näyttö – projektin nykytila

Tämä on projektin lyhyt tekninen ja toiminnallinen konteksti. Käyttö- ja asennusohjeiden ensisijainen lähde on [README.md](README.md). Palvelimen automaattipäivitys on dokumentoitu tiedostossa [AUTO_UPDATE.md](AUTO_UPDATE.md).

## Tavoite ja nykyinen ratkaisu

Perheen näyttö kokoaa arjen olennaiset tiedot helposti vilkaistavaksi yhteiseksi näkymäksi: aika, sää, perheen kalenterit, lasten koulutiedot, joukkoliikenne ja muistettavat asiat.

**Nykyinen, toimivaksi todettu toteutus on kotiverkon selainpalvelu**, ei erillinen e-paperinäyttö:

- Raspberry Pi 5 (2 Gt), Raspberry Pi OS Lite 64-bit, toimii headless-palvelimena.
- `web_dashboard.py` tarjoaa dashboardin kodin Wi-Fi-/lähiverkkoon portissa 8080.
- Vanha Android-tabletti toimii yhteisenä kiosk-näyttönä. Perheenjäsenet voivat avata saman osoitteen kodin Wi-Fi-verkossa myös omilla laitteillaan.
- Reitittimen DHCP-varaus pitää Raspberry Pin lähiverkko-osoitteen vakaana. Tabletissa käytetään IP-osoitetta, koska `.local`-nimi oli epäluotettava.
- `family-dashboard.service` käynnistää `dashboard_supervisor.py`-valvojan bootissa. Palvelu ja näkymän toiminta käynnistyksen jälkeen on todettu kotikäytössä.

**E-ink-suunnitelmasta on luovuttu.** Repositorion `eInk`-nimi, vanhat ajurit, `family_13in3`-layoutin nimi sekä osa laitteistodokumentaatiosta ovat historiallisen kehityspolun perintöä. Niitä ei tarvitse toteuttaa tai testata nykyistä tabletin verkkonäkymää varten.

## Repositorio ja kehityshaara

- Repositorio: https://github.com/salajukk/eInk
- **Aktiivinen kehitys ja dokumentaatio: `main`**
- `family-dashboard-v1` yhdistettiin `main`-haaraan 15.11.2026. Vanha haara säilyy siirtymävaiheessa, jotta Raspberry Pi voidaan päivittää hallitusti. Sen jälkeen uusia ominaisuuksia kehitetään vain `main`-haaraan.
- Raspberry Pin jo asennettua Git-haaraa ei voi muuttaa GitHubista käsin. Kertaluonteinen siirto on dokumentoitu tiedostossa `AUTO_UPDATE.md`.

## Toiminnallinen rakenne

- `data/*.py` hakee ja puskuroi lähdetiedot.
- `render_family_13in3.py` piirtää pääasiallisen 960 × 680 kuvapohjaisen tietonäytön. Layoutin vanha nimi ei tarkoita e-paperin käyttöä.
- `web_dashboard.py` renderöi kuvan tiedostoon `output/dashboard.png` ja tarjoaa sen selaimelle. Samassa selainkuoressa ovat interaktiiviset lisänäkymät:
  - Raspberry Pi:n tilanäkymä (`/system`).
  - Kuukausikalenteri (`/calendar-month.json`).
  - Koulusta muistettavaa (`/school`, `/school-reminders.json`).
- Kiosk-tabletilla etusivu pysyy yhdellä ruudulla; lisänäkymissä voi pyyhkäistä ja vierittää.
- `dashboard_supervisor.py` pitää web-palvelun käynnissä ja ottaa GitHubista fast-forward-muutokset käyttöön. `main`-haaran versio seuraa oletuksena `origin/main`, kun Pi on siirretty tähän haaraan.

Pääkuva päivittyy oletuksena 30 sekunnin välein. Web-palvelin rajoittaa yleistä kalenteri-/säävälimuistia viiteen minuuttiin ja HSL-välimuistia yhteen minuuttiin.

## Tietolähteet ja ominaisuudet

Perheen kalenterit ja Wilman koulukalenterit luetaan yksityisistä iCal-syötteistä. Sää tulee Open-Meteosta, HSL-lähdöt Digitransitista ja yksinkertaiset muistutukset paikallisesta konfiguraatiosta. Ominaisuuksien kytkimet ovat `config.yaml`-tiedoston `features`-osiossa.

Koulusivulla esitetään Wilma-viesteistä johdettuja tehtäviä sekä suoraan Wilma-lähteistä kerättyjä läksyjä, kokeita ja merkintöjä. `wilma_nightly.py` päivittää paikallista kouluaineistoa ajastetusti. Eri data- ja AI-vaiheiden epäonnistumisten tulee säilyttää viimeisin toimiva tulos, ei korvata sitä virheellisellä sisällöllä. AI:n johtopäätökset tulee pystyä tarkistamaan alkuperäisestä viestistä.

Google Tasks -integraatio on mahdollinen jatkokehitysidea, ei nykyinen käytössä oleva toteutus.

## Kehityksen reunaehdot

1. Pidä jatkuvasti toimiva selain/kiosk-ratkaisu ensisijaisena. E-paperiyhteensopivuutta ei tarvitse optimoida uusissa ominaisuuksissa.
2. Säilytä pääruudun vilkaistavuus ja tabletin toimiva näkymä. Tee laajemmat, selattavat osiot erillisiin selainpohjaisiin näkymiin.
3. Pidä palvelu kotiverkossa. Älä lisää julkista internet-julkaisua tai porttiohjausta ilman erillistä tietoturvasuunnitelmaa.
4. Älä siirrä salaisia kalenterilinkkejä, Wilma-tunnuksia, API-avaimia tai kouluaineistoa versionhallintaan. `config.yaml` ja `cache/` pysyvät paikallisina.
5. Tee koodimuutokset `main`-haaraan, varmista testit tarvittaessa ja huomioi, että `dashboard_supervisor.py` ei asenna uusia Python-paketteja automaattisesti.
6. Älä muuta palvelimen paikallista haaraa automaattisesti koodipäivityksen yhteydessä; hallittu siirtyminen on erillinen ylläpitotoimi.

## Lisädokumentaatio

- [README.md](README.md) – nykyinen käyttö, arkkitehtuuri ja perusasennus
- [AUTO_UPDATE.md](AUTO_UPDATE.md) – palvelun käynnistys ja päivitykset
- [TABLET_MONTH_CALENDAR.md](TABLET_MONTH_CALENDAR.md) – kuukausikalenteri
- [SYSTEM_HEALTH.md](SYSTEM_HEALTH.md) – Raspberry Pin valvonta
- [WILMA_REMINDERS.md](WILMA_REMINDERS.md) – koulumuistutusten integraatio
- [FAMILY_DASHBOARD.md](FAMILY_DASHBOARD.md) – aikaisemman laitteistovaiheen dokumentointia; tarkista muutokset ensisijaisesti README:stä
