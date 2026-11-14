# Perheen näyttö

**Projektin nykyinen toteutus on kodin sisäverkossa toimiva perheen tietonäyttö.** Raspberry Pi 5 julkaisee näkymän selaimeen, vanha Android-tabletti toimii yhteisenä kiosk-näyttönä ja saman sivun voivat avata muutkin kodin Wi-Fi-verkon laitteet.

**E-ink-näyttösuunnitelmasta on luovuttu.** Repositorion nimi `eInk` on historiallinen.

## Aktiivinen toteutus

Käytössä oleva sovellus, sen koodi ja ajantasainen README ovat haarassa:

**[family-dashboard-v1 – Perheen näytön README](https://github.com/salajukk/eInk/blob/family-dashboard-v1/README.md)**

> **Huomaa:** tämä `main`-haara sisältää vanhan e-paperiversion lähdekoodin. Älä käytä tämän haaran käynnistysohjeita nykyisen selainpohjaisen perhenäytön asentamiseen. Vaihda haaraan `family-dashboard-v1`, jossa ovat esimerkiksi `web_dashboard.py` ja `dashboard_supervisor.py`.

### Käytössä olevan version hakeminen

~~~bash
git clone --branch family-dashboard-v1 https://github.com/salajukk/eInk.git
cd eInk
~~~

Lue sen jälkeen aktiivisen haaran README:stä asetukset, Raspberry Pi -palvelun käynnistäminen, tabletin kiosk-käyttö ja tietoturvaohjeet.

Nykyistä perhenäyttöä käytetään **vain luotetussa kotiverkossa**; sitä ei pidä avata suoraan julkiseen internetiin.
