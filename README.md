
# 🛒 Einkaufslisten-WebApp (Raspberry Pi lokal gehostet)

## 📌 Ziel

Diese WebApp dient dem einfachen und flexiblen Erstellen von Einkaufslisten. Sie wird lokal auf einem Raspberry Pi gehostet und kann über jedes Gerät im Heimnetzwerk (z. B. Smartphone-Browser) bedient werden. Der Fokus liegt auf Benutzerfreundlichkeit, Erweiterbarkeit und offline-naher Nutzung.

---

## 🧩 Funktionale Anforderungen

### 📦 Zutatenverwaltung (Ingredients)

- Zutaten können über eine Suchfunktion durchsucht und ausgewählt werden
- Zutaten lassen sich durch Antippen der Liste hinzufügen
- Neue Zutaten können über ein einfaches Eingabeprotokoll erstellt werden:
  - **Schritt 1:** Name eingeben
  - **Erweiterbar:** Kategorie (z. B. Obst, Backwaren), Makronährwerte (z. B. kcal, Proteine)

### 🍽️ Gerichteverwaltung (Meals)

- Gerichte bestehen aus mehreren Zutaten mit Mengenangaben
- Gerichte können gespeichert und später wiederverwendet werden
- Neue Gerichte können erstellt werden durch:
  - Eingabe eines Namens
  - Auswahl bestehender Zutaten (inkl. Mengen)
  - Hinzufügen neuer Zutaten (falls notwendig, über das gleiche Protokoll)

### 📝 Einkaufsliste

- Zusammenstellen der Einkaufsliste durch Auswahl einzelner Zutaten und/oder Gerichte
- Zutaten erscheinen mit Mengenangaben in der Liste
- Download der Einkaufsliste als **PDF**
- **Zwischenspeicherung** der Einkaufsliste:
  - Auch nach Stunden oder Neustart des Browsers ist die Liste noch verfügbar
  - Kein Datenverlust bei Verbindungsunterbrechungen

### 👥 Mehrbenutzerfähigkeit (zukünftig)

- Mehrere Personen können parallel Einkaufslisten verwalten
- Einführung eines einfachen **Usernamen-Systems**
- Jede Liste wird **benutzerspezifisch** gespeichert

---

## 🛠️ Technischer Überblick

- **Frontend:** React + Vite
- **Backend:** FastAPI (Python) + SQLite
- **Deployment:** Lokal auf Raspberry Pi, zugänglich per IP im Heimnetzwerk
- **Kommunikation:** REST API (JSON)
- **Speicherung:** Lokale SQLite-Datenbank (persistent)

---

## 🐳 Docker-Konfiguration

### Backend (FastAPI + SQLite)

```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ./backend:/app
      - db_data:/app/einkaufsliste.db  # persistente Datenbank
    ports:
      - "8000:8000"
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  db_data:
```

### Datenbankpersistenz

- Die SQLite-Datei wird dauerhaft im Volume `db_data` gespeichert
- Auch bei Neustart von Docker bleiben die Daten erhalten

---

## 🧪 Testdaten für die Entwicklung

Ein Script (`init_data.py`) fügt automatisch Beispielzutaten hinzu, wenn die Datenbank leer ist. Es wird beim App-Start automatisch ausgeführt, solange du im Entwicklungsmodus arbeitest.

Beispieldaten:

- Äpfel
- Brot
- Milch

Du kannst dies in `main.py` bei Bedarf deaktivieren oder über ein ENV-Flag steuern.

---

## 🌱 Erweiterungen (für spätere Versionen)

- Kategorien (z. B. sortieren nach Obst, Tiefkühl, etc.)
- Kalorien-/Nährwertangaben pro Zutat und Gericht
- Benutzeraccounts mit Passwörtern
- Teilen von Einkaufslisten (z. B. via QR-Code oder Link)
- Automatische Gruppierung der Liste für Supermarktgänge

---

## ✅ MVP-Ziele

Die erste Version der App soll folgende Kernfunktionen enthalten:

1. Zutaten durchsuchen, hinzufügen, neu anlegen
2. Einkaufsliste dynamisch erstellen
3. Gerichte erstellen und hinzufügen
4. PDF-Export der Einkaufsliste
5. Einkaufsliste persistent speichern (lokal je Nutzername)

---

## 🚀 Zielumgebung

Diese App ist primär für einen **lokalen Betrieb auf einem Raspberry Pi** gedacht. Einfache Bedienung über Smartphone oder PC im gleichen Netzwerk steht im Fokus. Internetverbindung ist nicht erforderlich.

---
