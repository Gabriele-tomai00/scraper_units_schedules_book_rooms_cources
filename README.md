# Custom Scraper for UniTS data

Custom scraper that downloads from the units portale the following data:
- address book (professors ecc.)
- courses list
- info rooms
- lessons calendar
- rooms calendar (with other events and not only lessons)


## Address book
You can see the data from here: https://portale.units.it/en/rubrica
<img src="./img_readme/address_book.png" style="width:80%; height:auto;">


Exemple of result (one entry)
```
{
    "nome": "Adamo Sergia",
    "role": "Professore Ordinario",
    "department": "Dipartimento di Studi Umanistici",
    "department_staff_url": "https://portale.units.it/it/ugov/organizationunit/27686",
    "phone": "0405584368",
    "email": "adamo@units.it",
    "last_updated": "14/03/2026",
    "doc_type": "rubrica personale/professori/staff dell'università"
}
```

## Courses list
You can see the data from here: https://www.units.it/catalogo-della-didattica-a-distanza

<img src="./img_readme/cources_list.png" style="width:80%; height:auto;">

Exemple of result (one entry)
```
  {
    "course_code": "041AR",
    "teams_code": "slw8irt",
    "degree_program_code": "AR03",
    "academic_year": "2025/2026",
    "teacher_name": "BEDON CHIARA",
    "teacher_id": "014686",
    "period": "S1",
    "course_name": "ANALISI DELLE STRUTTURE",
    "degree_program": "ARCHITETTURA",
    "degree_program_eng": "ARCHITECTURE",
    "last_update": "14/03/2026"
  }
```



## Info rooms
<img src="./img_readme/cources_list.png" style="width:80%; height:auto;">

Exemple of result (one entry)
```
{
  "room_name": "Aula 2.5 MIcroscopia",
  "room_code": "017_02",
  "site_name": "Palazzina T",
  "site_code": "BT01",
  "address": "Via Edoardo Weiss, 15",
  "floor": "PianoT",
  "room_type": "non definito",
  "capacity": 38,
  "accessible": false,
  "maps_url": "https://www.google.com/maps?q=45.660185354429466,13.80443422072853",
  "maps_embed_url": "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d815.80288698819!2d13.80443422072853!3d45.660185354429466!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x477b6b480db6f519%3A0x8d54533258604fb0!2sUniversit%C3%A0%20degli%20Studi%20di%20Trieste%20-%20Dipartimento%20di%20Scienze%20Mediche%20-%20Palazzina%20T!5e1!3m2!1sit!2sit!4v1743428037044!5m2!1sit!2sit",
  "occupancy_building_url": "https://orari.units.it/agendaweb/index.php?view=rooms&include=rooms&_lang=it&sede=BT01",
  "occupancy_room_url": "https://orari.units.it/agendaweb/index.php?view=rooms&include=rooms&_lang=it&sede=BT01&aula=017_02",
  "equipment": [
    {
      "name": "Rete wifi eduroam",
      "status": "DISPONIBILE"
    },
    {
      "name": "Rete cablata eduroam",
      "status": "DISPONIBILE"
    },
    {
      "name": "Proiettore",
      "status": "DISPONIBILE"
    }
  ],
  "scrape_ok": true,
  "room_url": "",
  "url": "https://orari.units.it/agendaweb/index.php?form-type=vetrina_aule&view=vetrina_aule&include=vetrina_aule&_lang=it&list=&week_grid_type=-1&ar_codes_=&ar_select_=&col_cells=0&empty_box=0&only_grid=0&highlighted_date=0&all_events=0&sede%5B%5D=BT01&aula%5B%5D=017_02"
}
```

## Lessons calendar
<img src="./img_readme/lessons_calendar.png" style="width:80%; height:auto;">

Exemple of result (one entry)
```
  {
    "department": "DipartimentodiFisica",
    "degree_program_code": "SM20",
    "degree_program_name": "FISICA (Bachelor Degree)",
    "subject_code": "EC462850",
    "subject_name": "ELETTRODINAMICA E RELATIVITA' SPECIALE",
    "study_year_code": "PDS0-2024|2",
    "curriculum": "2 - Comune with all other curricula of that course",
    "date": "2026-02-23",
    "start_time": "09:00",
    "end_time": "11:00",
    "room_code": "024_5",
    "room_name": "Aula A",
    "site_name": "Edificio F",
    "site_code": "AF01",
    "address": "Via Alfonso Valerio, 2",
    "professors": "CANTATORE GIOVANNI",
    "lesson_type": "N/A",
    "cancelled": "no",
    "url": "https://orari.units.it/agendaweb/index.php?view=easycourse&form-type=corso&include=corso&txtcurr=&anno=2025&scuola=DipartimentodiFisica&corso=SM20&anno2%5B%5D=PDS0-2024%7C2&visualizzazione_orario=cal&date=2026-03-01&periodo_didattico=&_lang=it&list=&week_grid_type=-1&ar_codes_=&ar_select_=&col_cells=0&empty_box=0&only_grid=0&highlighted_date=0&all_events=0&faculty_group=0"
  }
```



## Rooms calendar
<img src="./img_readme/rooms_occupation.png" style="width:80%; height:auto;">

Exemple of result (one entry)
```
  {
    "site_code": "CEN_IDRO",
    "room_code": "14304_001",
    "date": "2026-03-02",
    "last_update": "02-03-2026",
    "site_name": "Centrale Idrodinamica",
    "room_name": "Sala Plenaria",
    "start_time": "11:00",
    "end_time": "13:00",
    "name_event": "INFERMIERISTICA CLINICA NELLE MALATTIE CRONICO-DEGENERATIVE",
    "professors": "CLAUDIA FANTUZZI"
  }
```