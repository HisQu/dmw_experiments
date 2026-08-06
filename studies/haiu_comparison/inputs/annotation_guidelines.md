# Annotationrichtlinien für Historische Regesten

## Allgemeine Prinzipien

### 1. Ziel und Umfang der Annotation:

* Die Annotation von Regesten dient der strukturierten Erfassung relevanter Entitäten zur besseren Analyse und maschinellen Verarbeitung des Repertorium Germanicum (RG).    
* Annotiert werden all jene Begriffe bzw. Konzepte, die für die Modellierung der Sachverhalte im RG notwendig sind, insbesondere für solche, für die sich ein Forschungsinteresse in der wissenschaftlichen Literatur nachweisen lässt. Neben der Forschungsliteratur berücksichtigen wir ebenfalls die Ergebnisse einer von uns in der historischen Forschungsgemeinschaft durchgeführten Umfrage zu früheren, aktuellen und geplanten Forschungsvorhaben mit Bezug zum RG.   
* Nicht getaggte Inhalte können später dennoch durch KI-gestützte Verfahren erfasst werden.
* Annotiert werden ausschließlich Begriffe, die explizit im Regesttext vorkommen. Begriffe, die mitgedacht werden müssen, z.B. (prov.) de eccl., bleiben ungetaggt.  
* Wörter können auch mit mehreren Labels gleichzeitig versehen werden, z.B. presbiteros (Personengruppe, Kirchlicher_Stand, Kirchliches_Amt).  
* Abkürzungspunkte und Endpunkte nach der Quellenangabe sind Teil der Annotation und werden entsprechend mit ausgezeichnet.      

### 2. Kategorien:

* Die Annotation erfolgt derzeit anhand einer Vielzahl von **basalen Kategorien**, also kleinster logisch abgrenzbarer Einheiten im Regesttext.
* Behelfsmäßig sind diese Basiskategorien in fünf übergeordnete Kategorien gruppiert: Personen und Personengruppen, Akteur, Vita, Event und Varia. Diese dienen der besseren Übersichtlichkeit und Navigation innerhalb der Guidelines.
Perspektivisch werden diese übergeordneten Kategorien durch andere/weitere semantische Kategorien ersetzt bzw. ergänzt. Semantische Kategorien entstehen aus der Kombination mehrerer basaler Kategorien. Ein und dieselbe basale Einheit kann dabei mehreren semantischen Kategorien zugeordnet werden. Die semantischen Kategorien befinden sich aktuell im Aufbau und werden schrittweise in die Guidelines integriert.

### 3. Darstellung im Guidelines-Dokument:

* Der Fettdruck kennzeichnet, welche Wörter mit dem Kategorielabel getaggt werden sollen und welche nicht.    

## Strukturierung der Labels und Beispiele

* Jede Kategorie (Personen und Personengruppen, Akteur, Vita, Event, Varia) enthält eine Liste von Labels (Unterkategorien). * Für jedes Label werden "Standardbeispiele" (Standard Examples) und "Sonstige Beispiele" (Other Examples) aufgeführt.
* Jedes Beispiel umfasst den Kontext und das zu annotierende Textfragment, wobei das Fragment in doppelten Sternchen (`**`) eingeschlossen ist. Die erwartete Annotation wird im Format `[Type: Value]` angegeben. Bei Beispielen, die mehrere Annotationen ergeben, werden alle aufgeführt.

## Kategorien

### Kategorie: Personen und Personengruppen

In den Regesten erscheinen Personen sowohl explizit, d.h. namentlich genannt, als auch implizit, d.h. nicht namentlich genannt, in Form von Umschreibungen.


#### Label: Person_explizit

##### Beschreibung:
Eine Person_explizit liegt immer dann vor, wenn die Person mit "Vorname" und "Namenszusatz" auftritt. Gelegentlich werden Personen auch nur mit "Vorname" oder nur mit "Namenszusatz" genannt. Das Label "Person_explizit" beinhaltet alle Namensbestandteile.

##### Standard Examples:
* Text: **Johannes de Azel**   
  Annotation: [Type: Person_explizit, Value: "Johannes de Azel"]
  
#### Label: Vorname

##### Beschreibung:
Der "Vorname" ist ein Namensbestandteil von fast allen explizit genannten Personen.

##### Standard Examples:

* Text: **Johannes** de Azel  
  Annotation: [Type: Vorname, Value: "Johannes"]
* Text: **Henricus** de Bocholdia    
  Annotation: [Type: Vorname, Value: "Henricus"]
* Text: **Floora** relicta Magni Bootes armig.  
  Annotation: [Type: Vorname, Value: "Floora"] 



#### Label: Namenszusatz

##### Beschreibung:
Der "Namenszusatz" ist eine Sammelbezeichnung für eine Vielzahl möglicher Namensbestandteile, die meist auf einen "Vornamen" folgen. Sie werden gesammelt als "Namenszusatz" gelabelt. Gemeinsam mit "Vorname" konstituiert der "Namenszusatz" in den allermeisten Fällen die Kategorie "Person_explizit". Achtung: Nicht als "Namenszusatz" gelten kirchliche Ämter (Albertus el. Ratisp. /Angelus abb. mon. in Runa), weltliche Ämter (Antonius dux Brabantie), Identifikation über eine andere Person (Alexander nob. viri Semonithi ducis Masouie natus).

##### Standard Examples:

* Text: Johannes **de Azel**  
  Annotation: [Type: Namenszusatz, Value: "de Azel"]  
* Text: Achacius **Berolczhaimer**  
  Annotation: [Type: Namenszusatz, Value: "Berolczhaimer"]
* Text: Bertholdus **Schomaker al. dictus Dives**   
  Annotation: [Type: Namenszusatz, Value: "Schomaker al. dictus Dives"]
* Text: Bertholdus **Denen (Deynen) de Wildunghen**  
  Annotation: [Type: Namenszusatz, Value: "Denen (Deynen) de Wildunghen"]
* Text: Fridericum **Baecht iuniorem**  
  Annotation: [Type: Namenszusatz, Value: "Baecht iuniorem"]
* Text: **Florentin. nunc.**  
  Annotation: [Type: Namenszusatz, Value: "Florentin. nunc."]

##### Other Examples:
* Text: castrum **das Newhaus nunc.**   
  Annotation: [Type: Namenszusatz, Value: "das Newhaus nunc."]



#### Label: Papst

##### Beschreibung:
Die Päpste sind im Kontext des RG eine besonders relevante Ausformung der Klasse "Person_explizit" und werden deshalb separat getaggt. Die Namen der Päpste kommen dekliniert vor, z.B. "Bonifatio VIII" statt "Bonifatius VIII"; ebenso: "pape" statt "papa". Achtung: Nicht als "Papst" getaggt werden Patrozinien, die ohne die Ordinalzahl (z.B. VIII) oder den Zusatz "papa" vorkommen, z.B.: Bonifatii im Kontext "eccl. s. Bonifatii Halberstad.".

##### Standard Examples:

* Text: **Bonifatius IX.**  
  Annotation: [Type: Papst, Value: "Bonifatius IX."]
* Text: **papa**  
  Annotation: [Type: Papst, Value: "papa"]
  * **Häufigkeit:** 480x in den Bänden 1-9, pape: 5307x in den Bänden 1-9.
* Text: **Bonifatio VIII papa**  
  Annotation: [Type: Papst, Value: "Bonifatio VIII papa"]



#### Label: Person_implizit

##### Beschreibung:
Eine "Person_implizit" liegt vor, wenn eine einzelne Person nicht namentlich auftritt, sondern über ein Pronomen, eine Amtsbezeichnung oder eine andere als die namentliche Bezeichnung referenziert wird. Hiervon zu unterscheiden sind die Bezeichnungen von Personengruppen, die über Worte und Ausdrücke im Plural erfolgen (s. Kategorie: Personengruppe).

##### Standard Examples:
* Text: **eum** et successores suos in Magunt. provin.  
  Annotation: [Type: Person_implizit, Value: "eum"]  
* Text: supplic. **aep. Magunt.**  
  Annotation: [Type: Person_implizit, Value: "aep. Magunt."]



#### Label: Personengruppe

##### Beschreibung:
Eine "Personengruppe" liegt immer dann vor, wenn ein sprachlicher Ausdruck sich auf mehr als eine Person bezieht. Nicht im Label enthalten sind attributiv gebrauchte Adjektive oder Ähnliches (vgl. Standard Examples: successores suos).

##### Standard Examples:
* Text: eum et **successores** suos in Magunt. provin.  
  Annotation: [Type: Personengruppe, Value: "successores"]  
* Text: **legatos** natos cum plena potestate  
  Annotation: [Type: Personengruppe, Value: "legatos"]  
* Text: cum **30 pers.** de confess. elig.    
  Annotation: [Type: Personengruppe, Value: "30 pers."]  
* Text: **alii**  
  Annotation: [Type: Personengruppe, Value: "alii"]  
* Text: quidem **8000 et infra** lim. eccl. s. Nicolai  
  Annotation: [Type: Personengruppe, Value: "8000 et infra"]  
* Text: **6000 parochiani**  
  Annotation: [Type: Personengruppe, Value: "6000 parochiani"]  
* Text: et **commune** op. D. Traiect. dioc.  
  Annotation: [Type: Personengruppe, Value: "commune"]  



### Kategorie: Akteur



#### Label: Anhänger_Marker

##### Standard Examples:
* Text: **adher.**  
  Annotation: [Type: Anhänger_Marker, Value: "adher."]



#### Label: Arme_Person_Marker

##### Standard Examples:

* Text: **pauper**  
  Annotation: [Type: Arme_Person_Marker, Value: "pauper"]
* Text: **gratis pro deo**  
  Annotation: [Type: Arme_Person_Marker, Value: "gratis pro deo"]
* Text: **gratis**  
  Annotation: [Type: Arme_Person_Marker, Value: "gratis"]



#### Label: Delegierter_Richter_Marker

##### Standard Examples:

* Text: **iudex delegatus**  
  Annotation: [Type: Delegierter_Richter_Marker, Value: "iudex delegatus"]



#### Label: Exekutor_Marker

##### Standard Examples: executor

* Text: **executor**  
  Annotation: [Type: Exekutor_Marker, Value: "executor"]



#### Label: Familiar_Marker

##### Standard Examples:

* Text: **fam.** Antonii ep. Portuen. card.  
  Annotation: [Type: Familiar_Marker, Value: "fam."]
* Text: **acolit.** pape  
  Annotation: [Type: Familiar_Marker, Value: "acolit."]

##### Other Examples:

* Text: **parafrenarius** pape  
  Annotation: [Type: Familiar_Marker, Value: "parafrenarius pape"]
* Text: **(unknown)** pape  
  Annotation: [Type: Familiar_Marker, Value: "(unknown)"]
  * **Hinweis:** Neben den oben genannten Beispielen "acolit. pape" und "parafrenarius pape" kann es noch weitere Ämter geben, die im direkten Umfeld des Papstes ausgeübt werden. Diese kirchlichen Ämter, die im Regest durch die direkte Nähe zum Wort "pape" gekennzeichnet sind, werden hier durch den Platzhalter (unknown) bezeichnet.


#### Label: Fürsprecher_Marker

##### Standard Examples:

* Text: **supplic.** Johanne ep. Gurc.  
  Annotation: [Type: Fürsprecher_Marker, Value: "supplic."]



#### Label: Kollator_Marker

##### Standard Examples:

* Text: ad **coll.** epp.  
  Annotation: [Type: Kollator_Marker, Value: "coll."]



#### Label: Kollektor_Marker

##### Standard Examples:

* Text: Gotfridi Bochorn **collect.**  
  Annotation: [Type: Kollektor_Marker, Value: "collect."]



#### Label: Obligationsbeauftragter_Marker

##### Standard Examples:

* Text: **o.s.a.** per Johannem Scade  
  Annotation: [Type: Obligationsbeauftragter_Marker, Value: "o.s.a."]



#### Label: Patron_Marker

##### Standard Examples:

* Text: **patron.**  
  Annotation: [Type: Patron_Marker, Value: "patron."]



#### Label: Petent_Marker

##### Standard Examples:

* Text: **S** 579 228vs, L 605 5rs.  
  Annotation: [Type: Petent_Marker, Value: "S"]



#### Label: Prozessvorsteher_Marker

##### Beschreibung: 
Eine Person, die einem Gerichtsprozess vorsteht.  

##### Standard Examples:

* Text: **iud.**      
  Annotation: [Type: Prozessvorsteher_Marker, Value: "iud."]  
* Text: **iudex**    
  Annotation: [Type: Prozessvorsteher_Marker, Value: "iudex"]    
* Text: **official.** Minden. hab. pot. ab ep. Verden.   
  Annotation: [Type: Prozessvorsteher_Marker, Value: "official."]    
* Text: **offic.** Minden. perm. causa de par. eccl.  
  Annotation: [Type: Prozessvorsteher_Marker, Value: "offic."] 


#### Label: Student_Marker

##### Standard Examples:

* Text: in alma Urbe in iure can. **studens**: ref. disp. sup. incompat.    
  Annotation: [Type: Student_Marker, Value: "studens"]  
* Text: Adolffus de Nassauw **scol.** Trever. de disp. sup. def. nat.    
  Annotation: [Type: Student_Marker, Value: "scol."]  
  * **Hinweis:** Zu beachten ist, dass eine Person, die als **scol.** bezeichnet wird, nicht immer ein Student ist und somit in dem Fall auch nicht **scol.** als StudentMarker taggt werden darf. Hier ein Beispiel: Albertus Glenneman (Gleneman) **scol.** Colon. in 10 anno constitutus de can. et min. preb. eccl. ss. Petri et Andree Paderburn. vac. p. o. Jordani de Widonbunghe in curia 18 ian. 1426 S 201 223r.


#### Label: Subkollektor_Marker

##### Standard Examples:

* Text: ratione off. **subcollectorie** in dioc. Constant.  
  Annotation: [Type: Subkollektor_Marker, Value: "subcollectorie"]  
* Text:  fructuum camere ap. **subcollectoris** S 68 135 v.    
  Annotation: [Type: Subkollektor_Marker, Value: "subcollectoris"]  



#### Label: Tischgenosse_Marker

##### Standard Examples:

* Text: fam. **commensalis** Dominici [de Capranica]  
  Annotation: [Type: Tischgenosse_Marker, Value: "commensalis"]



#### Label: Zahlungsbeauftragter_Marker

##### Standard Examples:

* Text: oblig. sup. annat. ( **p.** mag. Henricum Erkel d. Hesse  
Annotation: [Type: Zahlungsbeauftragter_Marker, Value: "p."]  
* Text: **p. manus** Prothasii de Tabernis (19 fl. auri de cam. )  
Annotation: [Type: Zahlungsbeauftragter_Marker, Value: "p. manus"]



#### Label: Zeuge_Marker

##### Standard Examples:

* Text: Adolphus filius ducis Cleven. **testis**  
Annotation: [Type: Zeuge_Marker, Value: "testis"]  
* Text: **testis** super quadam oblig. 28 iul. 1409 M 8.  
Annotation: [Type: Zeuge_Marker, Value: "testis"]


  
### Kategorie: Vita

#### Label: Familienbeziehung

##### Beschreibung:
In den Regesten wird für viele Personen eine "Familienbeziehung" angegeben. Die unter den Examples gelisteten Beispiele können auch dekliniert vorkommen. Die deklinierten Formen sollen ebenfalls das Label "Familienbeziehung" erhalten, z.B. uxoris statt uxor.

##### Standard Examples:

* Text: Albertus de Smolsco presb. Wladislav. dioc. **nepos** aep. Gneznen.  
  Annotation: [Type: Familienbeziehung, Value: "nepos"]
  * **Häufigkeit:** 403x in den Bänden 1-9
* Text: **ux.**  
  Annotation: [Type: Familienbeziehung, Value: "ux."]
  * **Häufigkeit:** 1878x in den Bänden 1-2 und 5-9
* Text: **genitor**  
  Annotation: [Type: Familienbeziehung, Value: "genitor"]

##### Other Examples:

* Text: **uxor**  
  Annotation: [Type: Familienbeziehung, Value: "uxor"]
  * **Häufigkeit:** 936x in den Bänden 1-5 und 9
* Text: **filius**  
  Annotation: [Type: Familienbeziehung, Value: "filius"]
* Text: **filia**  
  Annotation: [Type: Familienbeziehung, Value: "filia"]
* Text: **pater**  
  Annotation: [Type: Familienbeziehung, Value: "pater"]
* Text: **frater**  
  Annotation: [Type: Familienbeziehung, Value: "frater"]
* Text: **relicta**  
  Annotation: [Type: Familienbeziehung, Value: "relicta"]
* Text: **natus** (unknown)  
  Annotation: [Type: Familienbeziehung, Value: "natus"]
  * **Hinweis:** (unknown) steht hier als Platzhalter für den Namen des Vaters, z.B. "Bernhardus natus Johannis Berlin", wobei Johannes Berlin der Vater von Bernhardus ist. Oder: "Alexander nob. viri Semonithi ducis Masouie natus", wobei Semonithus der Vater des Alexander ist.
* Text: **consanguineus**  
  Annotation: [Type: Familienbeziehung, Value: "consanguineus"]



#### Label: Sozialer_Stand

##### Beschreibung:
Der soziale Stand einer Person ergibt sich u.a. aus Angaben zu ihrer (nicht-)adligen Herkunft.

##### Standard Examples:

* Text: **de nob. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de nob. gen."]
* Text: **nob. viri xxx**  
  Annotation: [Type: Sozialer_Stand, Value: "nob. viri xxx"]
* Text: **de bar.**  
  Annotation: [Type: Sozialer_Stand, Value: "de bar."]

##### Other Examples:

* Text: **scol.**  
  Annotation: [Type: Sozialer_Stand, Value: "scol."]
* Text: **studens**  
  Annotation: [Type: Sozialer_Stand, Value: "studens"]
* Text: **baron. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "baron. gen."]
* Text: **de com. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de com. gen."]
* Text: **de mil.**  
  Annotation: [Type: Sozialer_Stand, Value: "de mil."]
* Text: **milit. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "milit. gen."]  
* Text: **de ducum et com. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de ducum et com. gen."]
* Text: **de comit. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de comit. gen."]
* Text: **de ducum et comit. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de ducum et comit. gen."]
* Text: **de ducum et marchionum gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de ducum et marchionum gen."]
* Text: **de ducis** natus  
  Annotation: [Type: Sozialer_Stand, Value: "de ducis"]
* Text: **nob.**  
  Annotation: [Type: Sozialer_Stand, Value: "nob."]
* Text: **mul.**  
  Annotation: [Type: Sozialer_Stand, Value: "mul."]
* Text: **mulier**  
  Annotation: [Type: Sozialer_Stand, Value: "mulier"]
* Text: **armig.**  
  Annotation: [Type: Sozialer_Stand, Value: "armig."]
* Text: **mil.**  
  Annotation: [Type: Sozialer_Stand, Value: "mil."]
* Text: **civ.**  
  Annotation: [Type: Sozialer_Stand, Value: "civ."]
* Text: **civis**  
  Annotation: [Type: Sozialer_Stand, Value: "civis"]
* Text: **domic.**  
  Annotation: [Type: Sozialer_Stand, Value: "domic."]
  * **Hinweis:** s. Notiz unten.   
* Text: **de milit. gen.**  
  Annotation: [Type: Sozialer_Stand, Value: "de milit. gen."]
* Text: **opid.**  
  Annotation: [Type: Sozialer_Stand, Value: "opid."]
* Text: **bar.**  
  Annotation: [Type: Sozialer_Stand, Value: "bar."]
  * **Hinweis:** Wenn kein Herrschaftsgebiet genannt wird; vgl. Weltliches_Amt.
* Text: **com.**  
  Annotation: [Type: Sozialer_Stand, Value: "com."]
  * **Hinweis:** Wenn kein Herrschaftsgebiet genannt wird; vgl. Weltliches_Amt.
* Text: **comes**  
  Annotation: [Type: Sozialer_Stand, Value: "comes"]
  * **Hinweis:** Wenn kein Herrschaftsgebiet genannt wird; vgl. Weltliches_Amt.
* Text: **dux**  
  Annotation: [Type: Sozialer_Stand, Value: "dux"]
  * **Hinweis:** Wenn kein Herrschaftsgebiet genannt wird; vgl. Weltliches_Amt.
* Text: **incola**  
  Annotation: [Type: Sozialer_Stand, Value: "incola"]
* Text: **parochianus**  
  Annotation: [Type: Sozialer_Stand, Value: "parochianus"] 



#### Label: Kirchlicher_Stand

##### Beschreibung:
Der kirchliche Stand ergibt sich aus dem Empfang der niederen Weihen (Lektor, Akoluth, Subdiakon etc.) und der höheren Weihen (Diakonat, Presbyterat, Episkopat); er schlägt sich auch in der generellen Unterscheidung zwischen Laien und Klerikern nieder (laic. = Laie; cler. = Kleriker).

##### Standard Examples:

* Text: **presb.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "presb."]
  * **Hinweis:** vgl. Kirchliches_Amt
* Text: **laic.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "laic."]
* Text: **in minore ord. constit.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "in minore ord. constit."]

##### Other Examples:

* Text: **cler.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "cler."]
* Text: **acol.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "acol."]
* Text: **lect.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "lect."]
  * **Hinweis:** selten, eher: Kirchliches_Amt, s. Notizen unten.
* Text: **subdiac.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "subdiac."]
* Text: **diac.**  
  Annotation: [Type: Kirchlicher_Stand, Value: "diac."]
  * **Hinweis:** vgl. Kirchliches_Amt



#### Label: Beruf

##### Beschreibung
Bei einigen Personen, vor allem bei Laien, werden Angaben zum Beruf gemacht.

##### Standard Examples:
* Text: **mercator**  
  Annotation: [Type: Beruf, Value: "mercator"]
* Text: **medicus**  
  Annotation: [Type: Beruf, Value: "medicus"]  



#### Label: Kirchliches_Amt

##### Beschreibung
Ein kirchliches Amt ist eine offizielle Stellung oder Funktion, die eine Person innerhalb der römisch-katholischen Kirche einnahm. Ein kirchliches Amt kann als Ehrenamt (z. B. Senior in einem Kollegiatsstift) ausgeübt werden oder mit Einnahmen (Pfründe) verbunden sein (z. B. Dekan in einem Kollegiatsstift).  
Durch die Implikation einer festen Stelle mit Einnahmen unterscheiden sich die hier in den Beispielen erfassten kirchlichen Ämter (z.B. presb. card. = Kardinalpriester mit einer Titelkirche) von den unter dem Label KirchlicherStand gesammelten kirchlichen Weihen (z.B. presb. = Priester, i.e. Person, die die Priesterweihe empfangen hat, aber eventuell keine Pfründe erhalten hat).   
Es wird sowohl der Amtsträger (decanus) als auch das Amt (decanatus) getaggt.

##### Standard Examples:

* Text: **can. et preb.**  
  Annotation: [Type: Kirchliches_Amt, Value: "can. et preb."]
  * **Hinweis:** s. Notizen unten.
* Text: **ep.**  
  Annotation: [Type: Kirchliches_Amt, Value: "ep."]
* Text: **benef.**  
  Annotation: [Type: Kirchliches_Amt, Value: "benef."]

##### Other Examples:

* Text: **patr.**  
  Annotation: [Type: Kirchliches_Amt, Value: "patr."]
* Text: **aep.**  
  Annotation: [Type: Kirchliches_Amt, Value: "aep."]
* Text: **epp.**  
  Annotation: [Type: Kirchliches_Amt, Value: "epp."]
* Text: **episc.**  
  Annotation: [Type: Kirchliches_Amt, Value: "episc."]
* Text: **antistes**  
  Annotation: [Type: Kirchliches_Amt, Value: "antistes"]
* Text: **el.**  
  Annotation: [Type: Kirchliches_Amt, Value: "el."]
* Text: **ordin.**  
  Annotation: [Type: Kirchliches_Amt, Value: "ordin."]
* Text: **decan.**  
  Annotation: [Type: Kirchliches_Amt, Value: "decan."]
* Text: **dec.**  
  Annotation: [Type: Kirchliches_Amt, Value: "dec."]  
* Text: **archidiac.**  
  Annotation: [Type: Kirchliches_Amt, Value: "archidiac."]
* Text: **vic.**  
  Annotation: [Type: Kirchliches_Amt, Value: "vic."]
* Text: **abb.**  
  Annotation: [Type: Kirchliches_Amt, Value: "abb."]
* Text: **abbat.**  
  Annotation: [Type: Kirchliches_Amt, Value: "abbat."]
* Text: **cant.**  
  Annotation: [Type: Kirchliches_Amt, Value: "cant."]
* Text: **cust.**  
  Annotation: [Type: Kirchliches_Amt, Value: "cust."]
* Text: **custod.**  
  Annotation: [Type: Kirchliches_Amt, Value: "custod."]
  * **Hinweis:** Ganz selten auch Laien.
* Text: **prepos.**  
  Annotation: [Type: Kirchliches_Amt, Value: "prepos."]
* Text: **prep.**  
  Annotation: [Type: Kirchliches_Amt, Value: "prep."]
* Text: **scolast.**  
  Annotation: [Type: Kirchliches_Amt, Value: "scolast."]
* Text: **rect.**  
  Annotation: [Type: Kirchliches_Amt, Value: "rect."]
* Text: **lect.**  
  Annotation: [Type: Kirchliches_Amt, Value: "lect."]
  * **Hinweis:** Lektor im Kloster, selten: Kirchlicher_Stand, s. Notizen unten.
* Text: **thesaur.**  
  Annotation: [Type: Kirchliches_Amt, Value: "thesaur."]
* Text: **monach.**  
  Annotation: [Type: Kirchliches_Amt, Value: "monach."]
* Text: **monialis**  
  Annotation: [Type: Kirchliches_Amt, Value: "monialis."]
* Text: **dign.**  
  Annotation: [Type: Kirchliches_Amt, Value: "dign."]
  * **Hinweis:** = Höhere Ämter in einem Kapitel: Propst, Dekan, Scholaster.
* Text: **can.**  
  Annotation: [Type: Kirchliches_Amt, Value: "can."]
* Text: **preb.**  
  Annotation: [Type: Kirchliches_Amt, Value: "preb."]
* Text: **can. sub expect. preb.**  
  Annotation: [Type: Kirchliches_Amt, Value: "can. sub expect. preb."]
* Text: **can. et preb. ac supplem.**  
  Annotation: [Type: Kirchliches_Amt, Value: "can. et preb. ac supplem."]
* Text: **canonicatus seu prebenda**  
  Annotation: [Type: Kirchliches_Amt, Value: "canonicatus seu prebenda"]
* Text: **card.**  
  Annotation: [Type: Kirchliches_Amt, Value: "card."]
* Text: **presb. card.**  
  Annotation: [Type: Kirchliches_Amt, Value: "presb. card."]
  * **Hinweis:** Vgl. Kirchlicher_Stand
* Text: **diac. card.**  
  Annotation: [Type: Kirchliches_Amt, Value: "diac. card."]
  * **Hinweis:** Vgl. Kirchlicher_Stand
* Text: **ep. card.**  
  Annotation: [Type: Kirchliches_Amt, Value: "ep. card."]
  * **Hinweis:** Vgl. Kirchlicher_Stand
* Text: **vic. generalis**  
  Annotation: [Type: Kirchliches_Amt, Value: "vic. generalis"]
* Text: **mag. gen.**  
  Annotation:[Type: Kirchliches_Amt, Value: "mag. gen."]
* Text: **precept.**  
  Annotation:[Type: Kirchliches_Amt, Value: "precept."]
* Text: **capellan.**  
  Annotation:[Type: Kirchliches_Amt, Value: "capellan."]
* Text: **cap.**  
  Annotation:[Type: Kirchliches_Amt, Value: "cap."]
* Text: **succentor**  
  Annotation:[Type: Kirchliches_Amt, Value: "succentor"]
* Text: **capn.**  
  Annotation:[Type: Kirchliches_Amt, Value: "capn."] 
* Text: **benef. curato**  
  Annotation: [Type: Kirchliches_Amt, Value: "benef. curato"]
* Text: **benef. s. c.**  
  Annotation: [Type: Kirchliches_Amt, Value: "benef. s. c."]
* Text: **benef. c. c.**  
  Annotation: [Type: Kirchliches_Amt, Value: "benef. c. c."]
  * **Hinweis:** c.c. kann in seltenen Fällen im Kontext einer Dispens wegen def. nat. auch für den Ehestand der Eltern stehen; c. = conjugatus bzw. conjugata.
* Text: **prior**  
  Annotation: [Type: Kirchliches_Amt, Value: "prior"]
  


#### Label: Kuriales_Amt

##### Beschreibung:
Ein kuriales Amt ist eine offizielle Stellung oder Funktion, die eine Person an der römischen Kurie einnahm. Es wird sowohl der Amtsträger als auch das Amt getaggt. Achtung: Manche Positionen kommen auch außerhalb der Kurie an kirchlichen und weltlichen Höfen vor, sodass sich die genaue Zuschreibung des Labels nur aus dem Kontext ergibt (so z.B. beim Notar).

##### Standard Examples:

* Text: **abbr.**  
  Annotation: [Type: Kuriales_Amt, Value: "abbr."]
* Text: **administr.**  
  Annotation: [Type: Kuriales_Amt, Value: "administr."]
* Text: **aud.**  
  Annotation: [Type: Kuriales_Amt, Value: "aud."]

##### Other Examples:

* Text: **cancell.**  
  Annotation: [Type: Kuriales_Amt, Value: "cancell."]
* Text: **cubic.**  
  Annotation: [Type: Kuriales_Amt, Value: "cubic."]
* Text: **cursor**  
  Annotation: [Type: Kuriales_Amt, Value: "cursor"]
* Text: **not.**  
  Annotation: [Type: Kuriales_Amt, Value: "not."]
* Text: **nunt.**  
  Annotation: [Type: Kuriales_Amt, Value: "nunt."]
* Text: **offic.**  
  Annotation: [Type: Kuriales_Amt, Value: "offic."]
* Text: **procur.**  
  Annotation: [Type: Kuriales_Amt, Value: "procur."] 
* Text: **proc.**  
  Annotation: [Type: Kuriales_Amt, Value: "proc."]
* Text: **proc.** ap. sed.  
  Annotation: [Type: Kuriales_Amt, Value: "proc."]
* Text: **prothonot.**  
  Annotation: [Type: Kuriales_Amt, Value: "prothonot."]
* Text: **refer.**  
  Annotation: [Type: Kuriales_Amt, Value: "refer."]
* Text: **script.**  
  Annotation: [Type: Kuriales_Amt, Value: "script."]
* Text: **script. litt. ap.**  
  Annotation: [Type: Kuriales_Amt, Value: "script. litt. ap."]
* Text: **secret.**  
  Annotation: [Type: Kuriales_Amt, Value: "secret."]
* Text: **secr.**  
  Annotation: [Type: Kuriales_Amt, Value: "secr."]
* Text: **tab.**  
  Annotation: [Type: Kuriales_Amt, Value: "tab."]
* Text: **tab. off.**  
  Annotation: [Type: Kuriales_Amt, Value: "tab. off."]



#### Label: Weltliches_Amt

##### Beschreibung:
Ein weltliches Amt ist eine offizielle Stellung oder Funktion, die eine Person im höfischen Kontext (Fürstenhof, Bischofshof etc.) oder als städtischer Funktionsträger (Bürgermeister, Kanzler einer städtischen Kanzlei, Zunftmeister) einnahm.

##### Standard Examples:

* Text: **imp.**  
  Annotation: [Type: Weltliches_Amt, Value: "imp."]
* Text: **rex**  
  Annotation: [Type: Weltliches_Amt, Value: "rex"]

##### Other Examples:

* Text: **bar.**  
  Annotation: [Type: Weltliches_Amt, Value: "bar."]
  * **Hinweis:** Wenn ein Herrschaftsgebiet genannt wird, ansonsten: Sozialer_Stand.
* Text: **dux**  
  Annotation: [Type: Weltliches_Amt, Value: "dux."]
  * **Hinweis:** Wenn ein Herrschaftsgebiet genannt wird, ansonsten: Sozialer_Stand.
* Text: **com.**  
  Annotation: [Type: Weltliches_Amt, Value: "com."]
  * **Hinweis:** Wenn ein Herrschaftsgebiet genannt wird, ansonsten: Sozialer_Stand.
* Text: **comes**  
  Annotation: [Type: Weltliches_Amt, Value: "comes"]
  * **Hinweis:** Wenn ein Herrschaftsgebiet genannt wird, ansonsten: Sozialer_Stand.
* Text: **patron.**  
  Annotation: [Type: Weltliches_Amt, Value: "patron."]
* Text: **imperator**    
  Annotation: [Type: Weltliches_Amt, Value: "imperator"]
* Text: **rex elect.**    
  Annotation: [Type: Weltliches_Amt, Value: "rex elect."]
* Text: **proconsul**    
  Annotation: [Type: Weltliches_Amt, Value: "proconsul"]
* Text: **consul**    
  Annotation: [Type: Weltliches_Amt, Value: "consul"]
* Text: **burggravius**    
  Annotation: [Type: Weltliches_Amt, Value: "burggravius"]  
* Text: **scult.**  
  Annotation: [Type: Weltliches_Amt, Value: "scult."]  



#### Label: Akademischer_Grad

##### Standard Examples:

* Text: **licent.**  
  Annotation: [Type: Akademischer_Grad, Value: "licent."]
* Text: **bac.** in decr.  
  Annotation: [Type: Akademischer_Grad, Value: "bac."]

##### Other Examples:

* Text: **lic.**   
  Annotation: [Type: Akademischer_Grad, Value: "lic."]
  * **Hinweis:** Nur selten steht lic. für das Lizenziat, i.d.R. nur in Verbindung mit einem Namen. Häufiger steht es für die päpstliche Lizenz und wird dann als Event getaggt.
* Text: **mag.**  
  Annotation: [Type: Akademischer_Grad, Value: "mag."]
* Text: decr.**doct.**  
  Annotation: [Type: Akademischer_Grad, Value: "doct."]
* Text: theol. **profes.**  
  Annotation: [Type: Akademischer_Grad, Value: "profes."]


#### Label: Studienfach

##### Standard Examples:
* Text: mag. **in art.**    
  Annotation: [Type: Studienfach, Value: "in art."]
* Text: **decr.** doct.   
  Annotation: [Type: Studienfach, Value: "decr."]
* Text: lic. **in leg.**    
  Annotation: [Type: Studienfach, Value: "in leg."]
* Text: lic. **in iure can.**    
  Annotation: [Type: Studienfach, Value: "in iure can."]



#### Label: Orden

##### Beschreibung: 
Ausdruck der Zugehörigkeit zu einer religiösen Ordensgemeinschaft. Hinweis: Und deren Variationen (z.B. o. Cist.; Cist. ord.). Bitte ergänzen!

##### Standard Examples:

* Text: **o. s. Ant.**  
  Annotation: [Type: Orden, Value: "o. s. Ant."]
* Text: **o. s. Aug.**  
  Annotation: [Type: Orden, Value: "o. s. Aug."]
* Text: **o. s. Ben.**  
  Annotation: [Type: Orden, Value: "o. s. Ben."]

##### Other Examples:

* Text: **o. cist.**  
  Annotation: [Type: Orden, Value: "o. cist."]
* Text: **o. fr. herem. s. Aug.**  
  Annotation: [Type: Orden, Value: "o. fr. herem. s. Aug."]
* Text: **o. s. Ant.**  
  Annotation: [Type: Orden, Value: "o. s. Ant."]
* Text: **o. s. Clare**  
  Annotation: [Type: Orden, Value: "o. s. Clare"]
* Text: **o. Carm.**  
  Annotation: [Type: Orden, Value: "o. Carm."]
* Text: **o. Cartus.**  
  Annotation: [Type: Orden, Value: "o. Cartus."]
* Text: **o. Clun.**  
  Annotation: [Type: Orden, Value: "o. Clun."]
* Text: **o. fr. min.**  
  Annotation: [Type: Orden, Value: "o. fr. min."]
* Text: **o. pred.**  
  Annotation: [Type: Orden, Value: "o. pred."]
* Text: **o. Prem.**  
  Annotation: [Type: Orden, Value: "o. Prem."]



### Kategorie: Event


### Gnadenerweis

Hinweis: Die Unterklassen der Kategorie Gnadenerweis werden kontinuerlich weiterentwickelt. In Zukunft werden alle Gnadenerweise einheitlich mit deutschsprachigen Labels erscheinen.

#### Label: Abolitio

##### Beschreibung:
Tilgung, z.B. von Inhabilität

##### Standard Examples:

* Text: **m. abol. inhabil.**  
  Annotation: [Type: Abolitio, Value: "m. abol. inhabil."]
* Text: **abol. inhabil.**  
  Annotation: [Type: Abolitio, Value: "abol. inhabil."]
* Text: **abol. macule infamie**  
  Annotation: [Type: Abolitio, Value: "abol. macule infamie."]


#### Label: Absolutio

##### Beschreibung:
Absolution

##### Standard Examples:

* Text: **absol.**  
  Annotation: [Type: Absolutio, Value: "absol."]
* Text: **m. absol.**  
  Annotation: [Type: Absolutio, Value: "m. absol."]
* Text: **m. absol.** a sent. excom.  
  Annotation: [Type: Absolutio, Value: "m. absol."]

##### Other Examples:

* Text: **absol.** a matrim. C. gentili et quasi pagano contracto  
  Annotation: [Type: Absolutio, Value: "absol."]
* Text: **absol.**, quod olim …  
  Annotation: [Type: Absolutio, Value: "absol."]



#### Label: Aggravatio

##### Beschreibung:
Verstärkung einer Strafe

##### Standard Examples:

* Text: **m. aggrav. sent.**  
  Annotation: [Type: Aggravatio, Value: "m. aggrav. sent."]
* Text: **m. aggrav. excom. sent.**  
  Annotation: [Type: Aggravatio, Value: "m. aggrav. excom. sent."]
* Text: **m. aggravandi sent.**  
  Annotation: [Type: Aggravatio, Value: "m. aggravandi sent."]



#### Label: alternativa_facultas

##### Beschreibung: 
"Fakultät für Bischöfe zur alternierenden Besetzung von Pfründen" (Bearbeitungshinweise, S. 67)

##### Standard Examples: 

* Text: motu pr. de **alternativa** videlicet fac. disponendi sup. benef. vacat.  
  Annotation: [Type: alternativa_facultas, Value: "alternativa"]



#### Label: antelatio

##### Beschreibung: 
"Eine weitere Möglichkeit, sich gegenüber Konkurrenten eine Vorrangstellung zu verschaffen, wird durch die „antelatio“ geschaffen, die der Bevorzugung durch „prerogatio“ gleicht." (Bearbeitungshinweise, S. 66)

##### Standard Examples: 

* Text: de **antelatione**  
  Annotation: [Type: antelatio, Value: "antelatione"]


#### Label: Beichtprivileg

##### Beschreibung: 
Erlaubnis, sich seinen Beichtvater selbst zu wählen; entgegen dem Pfarrzwang.

##### Standard Examples:
* Text: gratia de **confess. elig.**  
  Annotation: [Type: Beichtprivileg, Value: "confess. elig."]
* Text: de **confess. elig.**  
  Annotation: [Type: Beichtprivileg, Value: "confess. elig."]



#### Label: Butterbrief

##### Beschreibung: 
Dispens von Fastenvorschriften.

##### Standard Examples: 

* Text: m. disp. ut **lacticiniis vesci** val.    
  Annotation: [Type: Butterbrief, Value: "lacticiniis vesci"]



#### Label: Cassatio

##### Beschreibung:
Ungültigkeitserklärung

##### Standard Examples:

* Text: **cass.**  
  Annotation: [Type: Cassatio, Value: "cass."]
* Text: **m. cass.** litt.  
  Annotation: [Type: Cassatio, Value: "m. cass."]
* Text: **cass.** pensionis  
  Annotation: [Type: Cassatio, Value: "cass."]

  

#### Label: Collatio

##### Beschreibung: 
Ist die Besetzung einer Pfründe.

##### Standard Examples: 

* Text: **coll.**  
  Annotation: [Type: Collatio, Value: "coll."]



#### Label: Concessio

##### Beschreibung:
Verleihung / Erlaubnis = Lizenz (?)

##### Standard Examples:

* Text: **conc. transgr.**  
  Annotation: [Type: Concessio, Value: "conc. transgr."]
  * **Hinweis:** vgl. Licentia -> lic. transgr.



#### Label: Confirmatio

##### Beschreibung:
Bestätigung

##### Standard Examples:

* Text: **conf.**  
  Annotation: [Type: Confirmatio, Value: "conf."]


#### Label: de_advoc

##### Beschreibung: 
Die Verteidigung vor Gericht übernehmen.

##### Standard Examples: 

* Text: de **advoc.** et committ. causam in cur.   
  Annotation: [Type: de_advoc, Value: "advoc."]



#### Label: de_benef.

##### Beschreibung: 
Gnadenerweis mit Benefizialthematik.

##### Standard Examples: 

* Text: de **benef.** Leod. dioc.  
  Annotation: [Type: de_benef., Value: "benef."]



#### Label: de_committendo

##### Beschreibung:
Auftrag zur weiteren Bearbeitung eines Falles

##### Standard Examples:

* Text: de **committ.**  
  Annotation: [Type: de_committendo, Value: "committ."]



#### Label: Declaratio

##### Beschreibung:
Erklärung

##### Standard Examples:

* Text: **decl.**  
  Annotation: [Type: Declaratio, Value: "decl."]




#### Label: Declaratio_Litteras_Perinde_Valere

##### Beschreibung: 
Nachbesserung einer Supplik

##### Standard Examples: 

* Text: motu pr. de **perinde valere** gr. expect.   
  Annotation: [Type: Declaratio_Litteras_Perinde_Valere, Value: "perinde valere"]



#### Label: de_fruct._percip.

##### Beschreibung: 
Gnadenerweis mit Benefizialthematik.

##### Standard Examples: 

* Text: de **fruct. percip.** in absentia    
  Annotation: [Type: de_fruct._percip., Value: "fruct. percip."]



#### Label: de_loco_interdicto

##### Beschreibung: 
Erlaubnis, trotz Interdikts u.a. die Messe feiern zu dürfen.

##### Standard Examples: 

* Text: de **locis interdictis**    
  Annotation: [Type: de_loco_interdicto, Value: "locis interdictis"]


#### Label: de_n._prom.

##### Beschreibung: 
Erlaubnis, eine eigentlich notwendige Weihe aufschieben zu dürfen, z.B. wegen eines Studiums.

##### Standard Examples: 

* Text: de **n. prom.** ad 7 an.  
  Annotation: [Type: de_n._prom., Value: "n. prom."]




#### Label: de_n._resid.

##### Beschreibung: 
Erlaubnis, nicht am Ort seines Benefizes wohnhaft sein zu müssen; entgegen der Anwesenheitspflicht.

##### Standard Examples: 

* Text: **n. resid.** ad quinquennium    
  Annotation: [Type: de_n._resid., Value: "n. resid."]




#### Label: de_prom._ad_ord._extra_temp.

##### Beschreibung: 
Erlaubnis, die höheren Weihen schneller als kanonisch vorgesehen empfangen zu dürfen.

##### Standard Examples: 

* Text:  de lic. recip. ord. in curia **extra temp.**    
  Annotation: [Type: de_prom._ad_ord._extra_temp., Value: "extra temp."]



#### Label: de_visitatione_et_reformatione

##### Beschreibung: 
Besuch und Reform eines Klosters.

##### Standard Examples: 

* Text: de fac. **visitandi et reformandi** mon. exempta   
  Annotation: [Type: de_visitatione_et_reformatione, Value: "visitandi et reformandi"]



#### Label: Derogatio

##### Beschreibung: 
Klauseln, die andere Regelungen / Tatsachen außer Kraft setzen; vgl. das Label Non_Obstanz.

##### Standard Examples:

* Text: de **derog.**    
  Annotation: [Type: Derogatio, Value: "derog."]
* Text: c. **derog.**    
  Annotation: [Type: Derogatio, Value: "derog."]


#### Label: Dispensatio

##### Beschreibung:
Befreiung, Außerkraftsetzung kirchlicher Gesetze. Hinweis: Dieses Label soll nur dann vergeben werden, wenn eine andere als die hiernach aufgeführten Unterarten der Dispense auftaucht. Die Unterarten werden sukkzessive von uns aufgefüllt.

##### Standard Examples:

* Text: **disp.**    
  Annotation: [Type: Dispensatio, Value: "disp."]



#### Label: dispensatio_alia_beneficia

##### Beschreibung:
Dispens für den Erhalt mehrerer Benefizien.

##### Standard Examples:

* Text: de disp. ut d. Theordericus d. prepos. unac. **alio benef.** recip. valeat    
  Annotation: [Type: dispensatio_alia_beneficia, Value: "alio benef."]
* Text: de **uberiori** disp.  
  Annotation: [Type: dispensatio_alia_beneficia, Value: "uberiori"]



#### Label: dispensatio_ad_incompatibilia_beneficia

##### Beschreibung: 
Dispens für den Erhalt mehrerer inkompatibler Benefizien.

##### Standard Examples: 

* Text: ad aliud benef. **incompat.**      
  Annotation: [Type: dispensatio_ad_incompatibilia_beneficia, Value: "incompat."]



#### Label: dispensatio_super_def._nat.

##### Beschreibung: 
Dispens für einen Geburtsdefekt.

##### Standard Examples: 

* Text: disp. super **def. nat.**  
  Annotation: [Type: dispensatio_super_def._nat., Value: "def. nat."]
* Text: n.o. **def. nat. (p.s.)**  
  Annotation: [Type: dispensatio_super_def._nat., Value: "def. nat. (p.s.)"]



#### Label: dispensatio_def._et.

##### Beschreibung: 
Dispens für den Empfang der Weihen vor dem Mindestalter.

##### Standard Examples:

* Text: disp. super **def. etat.** et super prom. ad sacr. ord.   
  Annotation: [Type:  dispensatio_def._et., Value: "def. etat."]

  

#### Label: dispensatio_super_impedimento_matrimonii

##### Beschreibung: 
Dispens für ein Ehehindernis.

##### Standard Examples: 

* Text: disp. super **impedimento consang. pro matrimonio** contrahendo    
  Annotation: [Type: dispensatio_super_impedimento_matrimonii, Value: "impedimento consang. pro matrimonio"]



#### Label: dispensatio_super_irregularitate

##### Beschreibung: 
Dispens von der Irregularität.

##### Standard Examples: 

* Text: disp. super **irreg.**  
  Annotation: [Type: dispensatio_super_irregularitate, Value: "irreg."]



#### Label: visitatio_liminum_apostolorum

##### Beschreibung: 
Dispens von der Besuchspflicht in Rom.

##### Standard Examples: 

* Text: liberatur a **visit. liminum**  
  Annotation: [Type: visitatio_liminum_apostolorum, Value: "visit. liminum"]



#### Label: Erectio

##### Beschreibung:
Erlaubnis zur Errichtung einer neuen kirchlichen Institution oder der Erhebung einer Kaplanei/Vikarie zur Pfarrkirche bzw. Pfarrkirche zur Kollegiatkirche etc.

##### Standard Examples:

* Text: **m. erig.**  
  Annotation: [Type: Erectio, Value: "m. erig."]
* Text: **erig.**  
  Annotation: [Type: Erectio, Value: "erig."]
* Text: **m. instit.**  
  Annotation: [Type: Erectio, Value: "m. instit."]

##### Other Examples:

* Text: **erigere**  
  Annotation: [Type: Erectio, Value: "erigere"]
* Text: de **erectione**  
  Annotation: [Type: Erectio, Value: "erectione"]
* Text: **instit.**  
  Annotation: [Type: Erectio, Value: "instit."]
* Text: de **institutione**  
  Annotation: [Type: Erectio, Value: "institutione."]



#### Label: Exemptio

##### Beschreibung:
Befreiung, Ausnahmestellung

##### Standard Examples:

* Text: **exemt.** de iurisdictione ordin.  
  Annotation: [Type: Exemptio, Value: "exemt."]
* Text: **exempt.** de iurisdictione ordin.  
  Annotation: [Type: Exemptio, Value: "exempt."]
* Text: **exemptione** de iurisdictione ordin.  
  Annotation: [Type: Exemptio, Value: "exemptione"] 

##### Other Examples:

* Text: **exemtione** de iurisdictione ordin.  
  Annotation: [Type: Exemptio, Value: "exemtione"]



#### Label: Facultas

##### Beschreibung:
Erlaubnis. Vgl. Lizenz und Concessio (?). Hinweis: Dieses Label soll nur dann vergeben werden, wenn eine andere als die hiernach aufgeführten Unterarten der Facultas auftaucht. Die Unterarten werden sukkzessive von uns aufgefüllt. 

##### Standard Examples

* Text: **facult.**  
  Annotation: [Type: Facultas, Value: "facult."]


#### Label: facultas_absolvendi

##### Beschreibung: 
Die Vollmacht, in bestimmten Fällen absolvieren zu dürfen.

##### Standard Examples: 

* Text: **facult. absol.** in casibus, in quibus  
  Annotation: [Type: facultas_absolvendi, Value: "facult. absol."]
* Text: **facult. absol.** eos, qui…  
  Annotation: [Type: facultas_absolvendi, Value: "facult. absol."]
* Text: **facult. absol.** 100 person.  
  Annotation: [Type: facultas_absolvendi, Value: "facult. absol."]


#### Label: facultas_reconciliandi

##### Beschreibung: 
Die Vollmacht zur Wiederherstellung kirchlicher Reinheit oder Gemeinschaft, sei es durch die rituelle Reinigung verunreinigter Kirchenräume oder durch die Reintegration von Personen in die Kirche.

##### Standard Examples: 

* Text: de **fac. reconciliandi** d. eccl. et eius cimit.   
  Annotation: [Type: facultas_reconciliandi, Value: "fac. reconciliandi"]

#### Label: facultas_resignandi

##### Beschreibung: 
"Gelegentlich wird die generelle Erlaubnis erteilt, Pfründen zu resignieren oder zu tauschen. Diese Erlaubnis bezieht sich auch auf die künftig zu erwerbenden Benefizien, was im Regest nicht eigens zum Ausdruck gebracht wird." (Bearbeitungshinweise, S. 63f.)

##### Standard Examples: 

* Text: de disp. ut par. eccl. ut supra extra cur. **resignare** val.  
  Annotation: [Type: facultas_resignandi, Value: "resignare"]



#### Label: Habilitatio

##### Beschreibung:
Befähigung zur Ausübung einer Rechtshandlung

##### Standard Examples:

* Text: **habil.**  
  Annotation: [Type: Habilitatio, Value: "habil."]

##### Other Examples: 

* Text: **habilitatio**  
  Annotation: [Type: Habilitatio, Value: "habilitatio"]



#### Label: Incorporatio

##### Beschreibung:
Einverleibung einer kirchlichen Institution durch eine andere, vgl. unio.

##### Standard Examples:

* Text: **incorp.**  
  Annotation: [Type: Incorporatio, Value: "incorp."]



#### Label: Indulgentia

##### Beschreibung:
Indulgenz, Ablass

##### Standard Examples:

* Text: **indulg.**  
  Annotation: [Type: Indulgentia, Value: "indulg."]



#### Label: Indultum

##### Beschreibung: 
"Indultum ist wie gratia und declaratio ein sehr weit gefasster Begriff, der, soweit nicht die oben behandelten Fälle betroffen sind, von der Kanzlei für viele unterschiedliche Gnadenerweise gebraucht wird" (Bearbeitungshinweise, S. 57)

##### Standard Examples: 

* Text: c. **indulto** conferendi dign.   
  Annotation: [Type: Indultum, Value: "indulto"]



#### Label: Introductio

##### Beschreibung:
Einführung in die Besitztümer einer Pfründe

##### Standard Examples:

* Text: m. **introduc.** in possess.    
  Annotation: [Type: Introductio, Value: "introduc."]
* Text: in possessionem bonorum eorum eccl. **introducat**    
  Annotation: [Type: Introductio, Value: "introducat"]


#### Label: Licentia

##### Beschreibung:
Sondererlaubnis. Dieses Label soll nur dann vergeben werden, wenn eine andere als die hiernach aufgeführten Unterarten der Lizenzen auftaucht. Die Unterarten werden sukkzessive von uns aufgefüllt.

##### Standard Examples:

* Text: **lic.**  
  Annotation: [Type: Licentia, Value: "lic."]
* Text: **m. lic.**  
  Annotation: [Type: Licentia, Value: "m. lic."]



#### Label: licentia_celebrandi_ante_diem

##### Beschreibung: 
Erlaubnis, die Messe vor Tagesanbruch zu feiern.

##### Standard Examples: 

* Text: lic. de **ante diem**  
  Annotation: [Type: licentia_celebrandi_ante_diem, Value: "ante diem"]
* Text: lic. celebrandi missam **ante diem**  
  Annotation: [Type: licentia_celebrandi_ante_diem, Value: "ante diem"]



#### Label: licentia_visitandi_sepulchrum

##### Beschreibung: 
Die Erlaubnis, das heilige Grab in Jerusalem zu besuchen.

##### Standard Examples: 

* Text: lic. **visitandi Sepulcrum Dominicum**  
  Annotation: [Type: licentia_visitandi_sepulchrum, Value: "visitandi Sepulcrum Dominicum"]



#### Label: licentia_arrendandi_locandi

##### Beschreibung: 
"Die unter Sixtus IV. offensichtlich neu eingerichtete Möglichkeit zur (zeitlich befristeten) Weitergabe einer beliebigen Pfründe wird mit Dauer der Befristung angegeben" (Bearbeitungshinweise, S. 64)

##### Standard Examples: 

* Text: lic. fruct. **arrendandi**  
  Annotation: [Type: licentia_arrendandi_locandi, Value: "arrendandi"]
* Text: de lic. **locandi** agros mense ep.  
  Annotation: [Type: licentia_arrendandi_locandi, Value: "locandi"]
 


#### Label: licentia_demoliendi

##### Beschreibung: 
Erlaubnis zum (teilweisen) Abriss eines kirchlichen Gebäudes.

##### Standard Examples: 

* Text: de lic. **demoliendi** capel.   
  Annotation: [Type: licentia_demoliendi, Value: "demoliendi"]




#### Label: licentia_dicendi_horas_canonicas

##### Beschreibung: 
"Erlaubnis, das Beten des Breviers (der kanonischen Stunden) in der an der Kurie praktizierten verkürzten Form vorzunehmen." (Bearbeitungshinweise, S. 62)

##### Standard Examples: 

* Text: lic. **dicendi horas** more Romano  
  Annotation: [Type: licentia_dicendi_horas_canonicas, Value: "dicendi horas"]



#### Label: licentia_permutandi

##### Beschreibung: 
Die Erlaubnis, Benefizien zu tauschen.

##### Standard Examples: 

* Text: lic. **permutandi beneficia**   
  Annotation: [Type: licentia_permutandi, Value: "permutandi beneficia"]



#### Label: licentia_studendi

##### Beschreibung: 
Erlaubnis, zu studieren.

##### Standard Examples: 

* Text: de **lic. studendi** leg. civiles  
  Annotation: [Type: licentia_studendi, Value: "lic. studendi"]



#### Label: licentia_tacendi_super_defectu_natalium

##### Beschreibung: 
Die Erlaubnis, den eigenen Geburtsdefekt verschweigen zu dürfen.

##### Standard Examples: 

* Text: de lic. deinceps disp. **sup. def. nat. ( p., s. ) tacendi**  
  Annotation: [Type: licentia_tacendi_super_defectu_natalium, Value: "sup. def. nat. ( p., s. ) tacendi"]


#### Label: licentia_testandi

##### Beschreibung:
Die Erlaubnis, als Zeuge aufzutreten.

##### Standard Examples: 

* Text: de **lic. testandi**  
  Annotation: [Type: licentia_testandi, Value: "lic. testandi"]



#### Label: littera_conservatoria_bonorum

##### Beschreibung:
"Bei der littera conservatoria bonorum handelt es sich um einen allgemeinen Schutzbrief für Kirchen und Klöster. Es heißt im Regest nur: de conserv." (Bearbeitungshinweise, S. 64)

##### Standard Examples:

* Text: de **conserv.**  
  Annotation: [Type: littera_conservatoria_bonorum, Value: "conserv."]



#### Label: littera_testimonialis

##### Beschreibung: 
Beurkundung (meist) einer Weihe

##### Standard Examples: 

* Text: **litt. testimonialis**  
  Annotation: [Type: littera_testimonialis, Value: "litt. testimonialis"]



#### Label: littera_passus

##### Beschreibung:
Reiseerlaubnis und Schutzbrief

##### Standard Examples:

* Text: **litt. passus**  
  Annotation: [Type: littera_passus, Value: "litt. passus"]
* Text: **littera passus**  
  Annotation: [Type: littera_passus, Value: "littera passus"]



#### Label: Monitorium

##### Beschreibung:
Ermahnung durch den Papst

##### Standard Examples:

* Text: **monitorium penale**  
  Annotation: [Type: Monitorium, Value: "monitorium penale"]



#### Label: Moratorium

##### Beschreibung:
Zahlungsaufschub, Hauptsächlich in RG 10 (?)

##### Standard Examples:

* Text: de **moratorio**  
  Annotation: [Type: Moratorium, Value: "moratorio"]
* Text: **moratorium**  
  Annotation: [Type: Moratorium, Value: "moratorium"]



#### Label: mutatio_collatoris

##### Beschreibung: 
Nachbesserung einer Supplik: Änderung des Kollators

##### Standard Examples: 

* Text: motu pr. de **mutatione collationis** ad can. et preb.   
  Annotation: [Type: mutatio_collatoris, Value: "mutatione collationis"]



#### Label: Pensio

##### Beschreibung:
Verleihung und Modifizierung von Pensionsleistunen

##### Standard Examples:

* Text: de **reductione pensionis**  
  Annotation: [Type: Pensio, Value: "reductione pensionis"]
* Text: de **transl. pensionis**  
  Annotation: [Type: Pensio, Value: "transl. pensionis"]



#### Label: Plenarablass

##### Beschreibung: Erlaubnis des einmaligen vollkommenen Ablasses

##### Standard Examples:
* Text: de **rem. plen.**  
  Annotation: [Type: Plenarablass, Value: "rem. plen."]




#### Label: prerogatio_ad_instar_pape_familaris

##### Beschreibung: 
Vorrecht in der Weise der päpstlichen Familie = Ein Vorrecht, das einer Person oder Institution dieselben Rechte einräumt wie sie die Mitglieder der päpstlichen Familie haben.

##### Standard Examples: 

* Text: **prerog.** ad instrar pape fam.  
  Annotation: [Type: prerogatio_ad_instar_pape_familaris, Value: "prerog."]]


#### Label: prerogatio_pape_familiaris_in_absentia

##### Beschreibung:
Vorrecht: "Bei zu erwartender Abwesenheit von der Kurie suchen Papstfamiliaren eigens um die Fortdauer ihrer Prärogativen in absentia nach" (Bearbeitungshinweise, S. 65)

##### Standard Examples: 

* Text: **prerog. pape fam. in absentia**  
  Annotation: [Type: prerogatio_pape_familiaris_in_absentia, Value: "prerog. pape fam. in absentia"]



#### Label: Prorogatio

##### Beschreibung:
Fristverlängerung, Aufschub

##### Standard Examples:

* Text: **prorog.**  
  Annotation: [Type: Prorogatio, Value: "prorog."]
* Text: cum **prorog.** term. solut. ad 1 an. propter incertitudinem taxe  
  Annotation: [Type: Prorogatio, Value: "prorog."]



#### Label: einfache_provisio

##### Beschreibung: 
Gnadenbrief, kraft dessen ein Kirchenamt verliehen wird.

##### Standard Examples: 

* Text: **prov.**  
  Annotation: [Type: einfache_provisio, Value: "prov."]
* Text: **m. prov.**  
  Annotation: [Type: einfache_provisio, Value: "m. prov."]



#### Label: gratia_expectativa

##### Beschreibung: 
Verleihung der Anwartschaft auf eine Pfründe

##### Standard Examples: 

* Text: **gr. expect.**  
  Annotation: [Type: gratia_expectativa, Value: "gr. expect."]



#### Label: nova_provisio

##### Beschreibung: 
Bestätigung einer früheren provisio.

##### Standard Examples: 

* Text: **nova prov.**  
  Annotation: [Type: nova_provisio, Value: "nova prov."]


  
#### Label: provisio_si_neutri

##### Beschreibung:
"Bei der Provision si neutri handelt es sich gewissermaßen um eine besondere Form der nova provisio, nämlich im Zusammenhang mit einem Prozess, den der Supplikant über seine Pfründe gegen einen Gegner (adversarius) führt. Für den Fall, dass sich in dem Gerichtsverfahren herausstellt, dass keinem von beiden (si neutri) Prozessgegnern ein Recht an der strittigen Pfründe zukommt, möge der Papst den Supplikanten mit dieser Pfründe providieren. Bei der Form si neutri wird in der Narratio grundsätzlich genannt: 1. die Prozessinstanz, 2. der Gegner und 3. der Prozessgegenstand." (Bearbeitungshinweise, S. 47f.)

##### Standard Examples: 

* Text: **prov. si neutri**  
  Annotation: [Type: provisio_si_neutri, Value: "prov. si neutri"]



#### Label: provisio_si_nulli

##### Beschreibung: 
"Die Form „si nulli“ entspricht der „si neutri“ mit dem Unterschied, dass der Supplikant gegen mehrere Gegner prozessiert. Diese Gegner werden unter 2. contra .... aufgereiht, gleichgültig ob sie bei Prozessen mit mehreren Instanzen von Anfang an mit dabei waren." (Bearbeitungshinweise, S. 48)

##### Standard Examples: 

* Text: **prov. si nulli**  
  Annotation: [Type: provisio_si_nulli, Value: "prov. si nulli"]



#### Label: surrogatio_ad_ius

##### Beschreibung: 
"Bei einer surrogatio geht es ähnlich wie bei den Formen si neutri, si nulli um einen Prozess wegen einer Pfründe. Im Besonderen handelt es sich hier darum, dass der Prozessgegner aus irgendeinem Grunde aus dem Prozess ausscheidet und der Supplikant nun darum bittet, in alle Rechtsansprüche des Ausgeschiedenen an der strittigen Pfründe einrücken zu dürfen; verbunden wird diese Bitte häufig mit der Bitte um Provision mit besagter Pfründe." (Bearbeitungshinweise, S. 48)

##### Standard Examples: 

* Text: **surrog. ad iur.**  
  Annotation: [Type: surrogatio_ad_ius, Value: "surrog. ad iur."]



#### Label: Reformatio

##### Beschreibung:
Abänderung, Nachbesserung einer päpstlichen Gnade

##### Standard Examples:

* Text: **ref.**  
  Annotation: [Type: Reformatio, Value: "ref."]
* Text: **reformatio**  
  Annotation: [Type: Reformatio, Value: "reformatio"]



#### Label: Rehabilitatio

##### Beschreibung: 
Wiederherstellung der Befähigung zur Ausübung einer Rechtshandlung

##### Standard Examples: 

* Text: **rehab.**  
  Annotation: [Type: Rehabilitatio, Value: "rehab."]
* Text: **rehabilitatio**  
  Annotation: [Type: Rehabilitatio, Value: "rehabilitatio"]



#### Label: Reservatio

##### Beschreibung: 
Die Reservierung einer Pfründe / Kanonikats.

##### Standard Examples: 

* Text: motu pr. de **reserv.** can. et preb.  
  Annotation: [Type: Reservatio, Value: "reserv."]



#### Label: Revalidatio

##### Beschreibung:
Erklärung der Gültigkeit einer verfallenen Gnade

##### Standard Examples:

* Text: **reval.**  
  Annotation: [Type: Revalidatio, Value: "reval."]



#### Label: salvus_conductus

##### Beschreibung:
Geleitsbrief / Sicheres Geleit. Achtung: im Digitalisat von Band 3 falsch eingelesen als salc. statt salv.

##### Standard Examples:

* Text: **salv. cond.**  
  Annotation: [Type: salvus_conductus, Value: "salv. cond."]
* Text: **salvus conductus**  
  Annotation: [Type: salvus_conductus, Value: "salvus conductus"]
* Text: **salc. cond.**  
  Annotation: [Type: salvus_conductus, Value: "salc. cond."]



#### Label: TragbarerAltar

##### Beschreibung: 

##### Standard Examples:
* Text: gratia de **alt. port.**  
  Annotation: [Type: TragbarerAltar, Value: "alt. port."]
* Text: de **alt. port.**  
  Annotation: [Type: TragbarerAltar, Value: "alt. port."]


#### Label: Unio

##### Beschreibung: 
Aufnahme einer geistlichen Institution in eine andere, aber nur für einen gewissen Zeitraum. Vgl. Incorporatio (dauerhafte Aufnahme).

##### Standard Examples: 

* Text: **unio** eccl. Rigen.  
  Annotation: [Type: Unio, Value: "unio"]


#### Label: Verleihung_Insignien

##### Beschreibung: 
Die Verleihung bischöflicher Insignien ehrenhalber an Prälaten.

##### Standard Examples: 

* Text: conc. de usu **insign. pont.**  
  Annotation: [Type: Verleihung_Insignien, Value: "insign. pont."]


#### Label: Unklare_Gnade

##### Beschreibung: 
Nicht näher beschriebene oder unklare Gnadenerweise.

##### Standard Examples: 

* Text: supplic. **pro diversis**  
  Annotation: [Type: Unklare_Gnade, Value: "pro diversis"]

  
### Zahlungsverpflichtung

#### Label: Zahlungsverpflichtung

##### Beschreibung:
Angaben zu einer Zahlungsverpflichtung.

##### Standard Examples:

* Text: **oblig.**    
  Annotation: [Type: Zahlungsverpflichtung, Value: "oblig."] 



### Geldzahlung

#### Label: Geldzahlung

##### Beschreibung:
Angaben zu einer Geldzahlung.

##### Standard Examples:

* Text: **solv.**    
  Annotation: [Type: Geldzahlung, Value: "solv."] 



### Gerichtsprozess

#### Label: Gerichtsprozess

##### Beschreibung:
Angaben zu einem Gerichtsprozess.

##### Standard Examples:

* Text: **litig.**  
  Annotation: [Type: Gerichtsprozess, Value: "litig."]
* Text: **constit. iudices appellat.**    
  Annotation: [Type: Gerichtsprozess, Value: "constit. iudices appellat."]



### Treueschwur

#### Label: Treueschwur

##### Beschreibung:
Angaben zu einem Treueschwur.

##### Standard Examples:
* Text: **iuram. fidel.**    
  Annotation: [Type: Treueschwur, Value: "iuram. fidel."]



### Tod

#### Label: Tod

##### Beschreibung:
Angaben zum Tod einer Person.

##### Standard Examples:
* Text: vac. p. **o.**    
  Annotation: [Type: Tod, Value: "o."]
* Text: **defuncti**    
  Annotation: [Type: Tod, Value: "defuncti"]
* Text: **mori**   
  Annotation: [Type: Tod, Value: "o."]
* Text: Alheydis relicta **quond.** Johannis Sibowen   
  Annotation: [Type: Tod, Value: "quond."]


### Weihe

#### Label: Weihe

##### Beschreibung:
Angaben zum Weihempfang.

##### Standard Examples:
* Text: **prom.**  
  Annotation: [Type: Weihe, Value: "prom."]



### Resignation

#### Label: Resignation

##### Beschreibung:
Angaben zur Aufgabe einer Pfründe.

##### Standard Examples:
* Text: **resign.**  
  Annotation: [Type: Resignation, Value: "resign."]



### Entsendung

#### Label: Entsendung

##### Beschreibung:
Jemand beauftragt eine Person, irgendwohin zu gehen.
  
##### Standard Examples:
* Text: **destin.**    
  Annotation: [Type: Entsendung, Value: "destin."]


### ErlangungAmt

#### Label: Erlangung_eines_Amtes

##### Beschreibung:
Angaben zur Erlangung eines Amtes (assec. est); nicht identisch mit dem Gnadenerweis der bloßen Provision einer Pfründe.

##### Standard Examples:
* Text: **assec. est**  
  Annotation: [Type: Erlangung_eines_Amtes, Value: "assec. est"]
* Text: **indebite assec. fuit**  
  Annotation: [Type: Erlangung_eines_Amtes, Value: "indebite assec. fuit"]


### Pfründenentzug

#### Label: Pfründenentzug

##### Beschreibung:
Jemand, z.B. der Papst, entzieht jemandem Rechte/Pfründen etc. (privatio)

##### Standard Examples:
* Text: adherens Barth. **priv.** can. et preb.  
  Annotation: [Type: Pfründenentzug, Value: "priv."]



### Kategorie: Varia


#### Label: Kommissionsvermerk

##### Beschreibung:
Der Verweis darauf, dass ein Fall zur weiteren Bearbeitung an eine andere Person oder Institution weitergeleitet wird. Achtung: Es gibt es auch einen Gnadenerweis namens de committ., bei dem eine Kommission als Gnade erbeten wird.


##### Standard Examples:

* Text: **committ.** mag. Petro de Mera    
  Annotation: [Type: Kommissionsvermerk, Value: "committ."]

#### Label: Vakanzgrund

##### Beschreibung:
Gründe, die für die Vakanz einer Pfründe gegeben werden.

##### Standard Examples:

* Text: **vac. p. o.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. o."]
* Text: **vacat. p. o.**  
  Annotation: [Type: Vakanzgrund, Value: "vacat. p. o."]
  * **Hinweis:** Neben p.o., das als Abkürzung für per obitum am häufigsten vorkommt, gibt es in Band 1 und 3 des RG per ob. als Alternative und in Band 9 p.o. in curia.
* Text: **vac. p. prom.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. prom."]

##### Other Examples:

* Text: **vac. p. n. prom.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. n. prom."]
* Text: **vac. p. priv.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. priv."]
* Text: **vac. p. devol.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. devol."]
* Text: **vac. p. transgr.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. transgr."]
* Text: **vac. p. resign.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. resign."]
* Text: **vac. p. assec.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. assec."]
* Text: **vac. p. ingress. relig.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. ingress. relig."]
* Text: **vac. p. contract. matrim.**  
  Annotation: [Type: Vakanzgrund, Value: "vac. p. contract. matrim."]
* Text: **vac. ex eo quod** …  
  Annotation: [Type: Vakanzgrund, Value: "vac. ex eo quod"]



#### Label: Herrschaftsgebiet

##### Beschreibung:
Bezeichnungen für weltliche Herrschaftsgebiete, z.B. Herzogtümer.

##### Standard Examples:
* Text: **ducat.**  
  Annotation: [Type: Herrschaftsgebiet, Value: "ducat."]
* Text: **baron.**  
  Annotation: [Type: Herrschaftsgebiet, Value: "baron."]


#### Label: Stadt_Dorf

##### Beschreibung:
Bezeichnungen für Städte und Dörfer; die Begriffe sind nicht immer klar zu unterscheiden, deshalb bekommen sie ein Label.

##### Standard Examples:
* Text: **op.**  
  Annotation: [Type: Stadt_Dorf, Value: "op."]
* Text: **op. imp.**  
  Annotation: [Type: Stadt_Dorf, Value: "op. imp."]
* Text: **villa**  
  Annotation: [Type: Stadt_Dorf, Value: "villa"]
* Text: **civit.**  
  Annotation: [Type: Stadt_Dorf, Value: "civit."]


#### Label: Diözese

##### Beschreibung:
Eine kirchliche Verwaltungseinheit.

##### Standard Examples:

* Text: **Traiect. dioc.**  
  Annotation: [Type: Diözese, Value: "Traiect. dioc."]
* Text: **dioc. Traiect.**  
  Annotation: [Type: Diözese, Value: "dioc. Traiect."]


##### Other Examples:

* Text: **Magunt. dioc.**  
  Annotation: [Type: Diözese, Value: "Magunt. dioc."]
* Text: **Colon. dioc.**  
  Annotation: [Type: Diözese, Value: "Colon. dioc."]



#### Label: Institution

##### Beschreibung:
Kirchen, Klöster, Universitäten, etc.

##### Standard Examples:

* Text: **eccl.**  
  Annotation: [Type: Institution, Value: "eccl."]
* Text: **par. eccl.**  
  Annotation: [Type: Institution, Value: "par. eccl."]
* Text: **mon.**  
  Annotation: [Type: Institution, Value: "mon."]

##### Other Examples:

* Text: **capit.**  
  Annotation: [Type: Institution, Value: "capit."]
* Text: **capit. eccl.**  
  Annotation: [Type: Institution, Value: "capit. eccl."]
* Text: **fil. eccl.**  
  Annotation: [Type: Institution, Value: "fil. eccl."]
* Text: **fil. par. eccl.**  
  Annotation: [Type: Institution, Value: "fil. par. eccl."]
* Text: **colleg. eccl.**  
  Annotation: [Type: Institution, Value: "colleg. eccl."]
* Text: **capel.**  
  Annotation: [Type: Institution, Value: "capel."]
* Text: **cathedr.**  
  Annotation: [Type: Institution, Value: "cathedr."]
* Text: **conv.**  
  Annotation: [Type: Institution, Value: "conv."]
* Text: **ord.**  
  Annotation: [Type: Institution, Value: "ord."]
* Text: **cam.**  
  Annotation: [Type: Institution, Value: "cam."]
* Text: **penit.**  
  Annotation: [Type: Institution, Value: "penit."]
* Text: **pen.**  
  Annotation: [Type: Institution, Value: "pen."]
* Text: **abbatia**  
  Annotation: [Type: Institution, Value: "abbatia"]
* Text: **hosp. paup.**  
  Annotation: [Type: Institution, Value: "hosp. paup."]
* Text: **conv.** mon.  
  Annotation: [Type: Institution, Value: "conv."]
* Text: **dom.**  
  Annotation: [Type: Institution, Value: "dom."]
  * **Hinweis:** Achtung: dom. nur als Institution taggen, wenn es für domus steht, nicht für dominus.
* Text: **domus**  
  Annotation: [Type: Institution, Value: "domus"]
* Text: **preceptoria**  
  Annotation: [Type: Institution, Value: "preceptoria"]
* Text: **prioratus**  
  Annotation: [Type: Institution, Value: "prioratus"]  



#### Label: Exempter_Status

##### Beschreibung:
Information zur Beziehung einer kirchlichen Institution zur Kurie, insbesondere die direkte Unterstellung unter den Papst (Exemption). 

##### Standard Examples:

* Text: eccl. b. Marie castri Aldenburg. Rom. eccl. **immed. subiect.**  
  Annotation: [Type: Exempter_Status, Value: "immed. subiect."]



#### Label: Titelkirche

##### Beschreibung:
Kirchen, die Bischöfen, Priestern und Diakonen bei ihrer Kardinalsweihe zugeteilt werden. Ihre Anzahl ist finit. Man erkennt sie v.a. daran, dass in ihrer Nähe im Regest ein Kardinal genannt wird (ep. card., presb. card., diac. card.). In diesen Fällen wird ausnahmsweise darauf verzichtet, zusätzlich das Patrozinium oder den Ort als solche gesondert zu taggen.

##### Standard Examples:

* **Titelkirchen Kardinalbischöfe:**
  * Text: **Albanen.**  
    Annotation: [Type: Titelkirche, Value: "Albanen."]
  * Text: **Ostien. et Velletren.**  
    Annotation: [Type: Titelkirche, Value: "Ostien. et Velletren."]
  * Text: **Portuen. et s. Rufinae**  
    Annotation: [Type: Titelkirche, Value: "Portuen. et s. Rufinae"]
* **Titelkirchen Kardinalpriester:**
  * Text: **S. Anastasiae**  
    Annotation: [Type: Titelkirche, Value: "S. Anastasiae"]
  * Text: **Ss. XII Apostolorum**  
    Annotation: [Type: Titelkirche, Value: "Ss. XII Apostolorum"]
  * Text: **S. Balbinae**  
    Annotation: [Type: Titelkirche, Value: "S. Balbinae"]

##### Other Examples:

* **Titelkirchen Kardinalbischöfe:**
  * Text: **Praenestin.**  
    Annotation: [Type: Titelkirche, Value: "Praenestin."]
  * Text: **Sabinen.**  
    Annotation: [Type: Titelkirche, Value: "Sabinen."]
  * Text: **Tusculan.**  
    Annotation: [Type: Titelkirche, Value: "Tusculan."]
* **Titelkirchen Kardinalpriester:**
  * Text: **S. Caeciliae**  
    Annotation: [Type: Titelkirche, Value: "S. Caeciliae"]
  * Text: **S. Chrysogoni**  
    Annotation: [Type: Titelkirche, Value: "S. Chrysogoni"]
  * Text: **S. Clementis**  
    Annotation: [Type: Titelkirche, Value: "S. Clementis"]
  * Text: **Ss. IV Coronatorum**  
    Annotation: [Type: Titelkirche, Value: "Ss. IV Coronatorum"]
  * Text: **S. Crucis in Jerusalem**  
    Annotation: [Type: Titelkirche, Value: "S. Crucis in Jerusalem"]
  * Text: **S. Cyriaci**  
    Annotation: [Type: Titelkirche, Value: "S. Cyriaci"]
  * Text: **Ss. Joannis et Pauli**  
    Annotation: [Type: Titelkirche, Value: "Ss. Joannis et Pauli"]
  * Text: **S. Laurentii in Damaso**  
    Annotation: [Type: Titelkirche, Value: "S. Laurentii in Damaso"]
  * Text: **S. Laurentii in Lucina**  
    Annotation: [Type: Titelkirche, Value: "S. Laurentii in Lucina"]
  * Text: **S. Marcelli**  
    Annotation: [Type: Titelkirche, Value: "S. Marcelli"]
  * Text: **Ss. Marcellini et Petri**  
    Annotation: [Type: Titelkirche, Value: "Ss. Marcellini et Petri"]
  * Text: **S. Marci**  
    Annotation: [Type: Titelkirche, Value: "S. Marci"]
  * Text: **S. Mariae trans Tiberim**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae trans Tiberim"]
  * Text: **S. Martini in montibus**  
    Annotation: [Type: Titelkirche, Value: "S. Martini in montibus"]
  * Text: **Ss. Nerei et Achillei**  
    Annotation: [Type: Titelkirche, Value: "Ss. Nerei et Achillei"]
  * Text: **S. Nicolai ad (inter) imagines**  
    Annotation: [Type: Titelkirche, Value: "S. Nicolai ad (inter) imagines"]
  * Text: **S. Petri ad vincula**  
    Annotation: [Type: Titelkirche, Value: "S. Petri ad vincula"]
  * Text: **S. Praxedis**  
    Annotation: [Type: Titelkirche, Value: "S. Praxedis"]
  * Text: **S. Priscae**  
    Annotation: [Type: Titelkirche, Value: "S. Priscae"]
  * Text: **S. Pudentianae**  
    Annotation: [Type: Titelkirche, Value: "S. Pudentianae"]
  * Text: **S. Sabinae**  
    Annotation: [Type: Titelkirche, Value: "S. Sabinae"]
  * Text: **Ss. Silvestri et Martini**  
    Annotation: [Type: Titelkirche, Value: "Ss. Silvestri et Martini"]
  * Text: **S. Sixti**  
    Annotation: [Type: Titelkirche, Value: "S. Sixti"]
  * Text: **S. Stephani in Coelio monte**  
    Annotation: [Type: Titelkirche, Value: "S. Stephani in Coelio monte"]
  * Text: **S. Susannae**  
    Annotation: [Type: Titelkirche, Value: "S. Susannae"]
  * Text: **S. Vitalis**  
    Annotation: [Type: Titelkirche, Value: "S. Vitalis"]
* **Titelkirchen Kardinaldiakone:**
  * Text: **S. Adriani**  
    Annotation: [Type: Titelkirche, Value: "S. Adriani"]
  * Text: **S. Agathae**  
    Annotation: [Type: Titelkirche, Value: "S. Agathae"]
  * Text: **S. Angeli in foro piscium**  
    Annotation: [Type: Titelkirche, Value: "S. Angeli in foro piscium"]
  * Text: **Ss. Cosmae et Damiani**  
    Annotation: [Type: Titelkirche, Value: "Ss. Cosmae et Damiani"]
  * Text: **S. Eustachii**  
    Annotation: [Type: Titelkirche, Value: "S. Eustachii"]
  * Text: **S. Georgii ad velum aureum**  
    Annotation: [Type: Titelkirche, Value: "S. Georgii ad velum aureum"]
  * Text: **S. Luciae in Orthea (Silice)**  
    Annotation: [Type: Titelkirche, Value: "S. Luciae in Orthea (Silice)"]
  * Text: **S. Luciae in Septemsoliis**  
    Annotation: [Type: Titelkirche, Value: "S. Luciae in Septemsoliis"]
  * Text: **S. Mariae in Aquiro**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae in Aquiro"]
  * Text: **S. Mariae in Cosmedin**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae in Cosmedin"]
  * Text: **S. Mariae novae**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae novae"]
  * Text: **S. Mariae in Porticu**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae in Porticu"]
  * Text: **S. Mariae in via lata**  
    Annotation: [Type: Titelkirche, Value: "S. Mariae in via lata"]
  * Text: **S. Nicolai in carcere Tulliano**  
    Annotation: [Type: Titelkirche, Value: "S. Nicolai in carcere Tulliano"]
  * Text: **Ss. Sergii et Bacchi**  
    Annotation: [Type: Titelkirche, Value: "Ss. Sergii et Bacchi"]
  * Text: **S. Theodori**  
    Annotation: [Type: Titelkirche, Value: "S. Theodori"]
  * Text: **Ss. Viti et Modesti**  
    Annotation: [Type: Titelkirche, Value: "Ss. Viti et Modesti"]



#### Label: Patrozinium

##### Beschreibung:
Namenspatrone von Kirchen oder Institutionen.

##### Standard Examples:

* Text: **s. Jacobi**  
  Annotation: [Type: Patrozinium, Value: "s. Jacobi"]
* Text: **b. Marie**  
  Annotation: [Type: Patrozinium, Value: "b. Marie"]
* Text: **s. Johannis bapt.**  
  Annotation: [Type: Patrozinium, Value: "s. Johannis bapt."]

##### Other Examples:

* Text: **s. Johannis ev.**  
  Annotation: [Type: Patrozinium, Value: "s. Johannis ev."]
* Text: **s. crucis**  
  Annotation: [Type: Patrozinium, Value: "s. crucis"]  



#### Label: Objekt

##### Beschreibung:
Unspezifizierte Objekte

##### Standard Examples:

* Text: **alt.**  
  Annotation: [Type: Objekt, Value: "alt."]
* Text: **alt. port.**  
  Annotation: [Type: Objekt, Value: "alt. port."]


#### Label: Name_Ort

##### Beschreibung:
Namen von Städten, Dörfern, Regionen und Bergen (s. Notizen unten).

##### Standard Examples:

* Text: **Bodegrauen**  
  Annotation: [Type: Name_Ort, Value: "Bodegrauen"]
* Text: Novifori **Magdeburg.**  
  Annotation: [Type: Name_Ort, Value: "Magdeburg."]
* Text: in castro **Quernfort**  
  Annotation: [Type: Name_Ort, Value: "Quernfort"]
* Text: **Slesia**  
  Annotation: [Type: Name_Ort, Value: "Slesia"]  

##### Other Examples:
* Text: in **Rauhen** et in **Schlechthin Kulm** castris  
  Annotation: [Type: Name_Ort, Value: "Rauhen"]  
  Annotation: [Type: Name_Ort, Value: "Schlechthin Kulm"]  
* Text: **Civitasnova**  
  Annotation: [Type: Name_Ort, Value: "Civitasnova"]



#### Label: Kurie

##### Beschreibung:
Die Kurie ist an dem Ort, an dem der Papst ist.

##### Standard Examples:

* Text: apud. **cur.**  
  Annotation: [Type: Kurie, Value: "cur."]
* Text: **ap. sed.**  
  Annotation: [Type: Kurie, Value: "ap. sed."]


#### Label: Gebäude_Gebäudeteil

##### Beschreibung:
Bauwerk oder Teil eines Bauwerks

##### Standard Examples:
* Text: in **castro** Quernfort  
  Annotation: [Type: Gebäude_Gebäudeteil, Value: "castro"]
* Text: in **cripta** eccl. Spiren.  
  Annotation: [Type: Gebäude_Gebäudeteil, Value: "cripta"]
 


#### Label: Vorstadt

##### Beschreibung:
Ein Ort außerhalb der Stadtmauern (=Vorstadt) wird im RG über die Abkürzung "e. m." ("extra muros") angegeben.

##### Standard Examples:
* Text: eccl. s. Victoris **e. m.** Magunt.  
  Annotation: [Type: Vorstadt, Value: "e. m."]



#### Label: Konzil

##### Beschreibung:
Kirchliches Konzil / Synode

##### Standard Examples:

* Text: **concil.**  
  Annotation: [Type: Konzil, Value: "concil."]



#### Label: Expeditionsmodalitäten

##### Beschreibung:
In den Regesten werden manchmal Angaben dazu gemacht, wie der Gnadenbrief ausgestellt werden soll. 
- motu proprio: Drückt aus, dass ein Brief - im Gegensatz zum üblichen Reskriptionsverfahren – vom Papst selbst ausgeht; Ausdruck besonderen Wohlwollens.
- sola signatura: Es wird kein Gnadenbrief ausgestellt; die Genehmigung des Gesuches wird durch eine Unterschrift auf der Supplik angezeigt.
- rationi congruit: Vermerk, dass die Gnade bereits genehmigt worden war, aber vor dem Tod des Papstes nicht mehr expediert werden konnte.
- gratis: Die Expedition der Urkunde erfolgt kostenlos für den Petenten.

##### Standard Examples:

* Text: **motu pr.**  
  Annotation: [Type: Expeditionsmodalitäten, Value: "motu pr."]
* Text: **sola signatura**  
  Annotation: [Type: Expeditionsmodalitäten, Value: "sola signatura"]  



#### Label: Annaten

##### Beschreibung:
Zahlungen an den Papst für die Verleihung einer Pfründe.

##### Standard Examples:

* Text: **annat.**  
  Annotation: [Type: Annaten, Value: "annat."]
* Text: **annata**  
  Annotation: [Type: Annaten, Value: "annata"]



#### Label: Servitien

##### Beschreibung:
Zahlungen des Bischöfe und einiger Äbte an den Papst anlässlich ihrer Einsetzung.

##### Standard Examples:

* Text: **serv.**  
  Annotation: [Type: Servitien, Value: "serv."]
* Text: 5 min. **serv.**  
  Annotation: [Type: Servitien, Value: "serv."]
* Text: comm. **serv.**  
  Annotation: [Type: Servitien, Value: "serv."]



#### Label: Geldsumme

##### Beschreibung:
Geldbeträge in historischen Einheiten (Betrag und Währung).

##### Standard Examples:

* Text: **9 fl.**  
  Annotation: [Type: Geldsumme, Value: "9 fl."]
* Text: **4 m. arg.**  
  Annotation: [Type: Geldsumme, Value: "4 m. arg."]



#### Label: Dauer

##### Beschreibung:
Dauer eines Dispens, einer Pfründe etc.

##### Standard Examples:

* Text: **3 an.**  
  Annotation: [Type: Dauer, Value: "3 an."]
* Text: **perp.**  
  Annotation: [Type: Dauer, Value: "perp."]



#### Label: Non_Obstanz

##### Beschreibung:
Klauseln, die andere Regelungen / Tatsachen außer Kraft setzen; vgl. Derogatio.

##### Standard Examples:

* Text: **n. o.** can. et preb.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 4459x in den Bänden 1-9

##### Other Examples:

* Text: **n. o.** par. eccl.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 2665x in den Bänden 2-4 und 6-8
* Text: **n. o.** def. nat.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 1044x in den Bänden 2-4 und 6-8
* Text: **n. o.** perp. vicar.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 243x nur in den Bänden 7+8
* Text: **n. o.** perp. s. c. vicar.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 122x, nur in den Bänden 7-8
* Text: **n. o.** statut.  
  Annotation: [Type: Non_Obstanz, Value: "n. o."]
  * **Häufigkeit** 13x, nur in Band 3



#### Label: Datum

##### Beschreibung:
exakte oder ungefähre Datumsangaben

##### Standard Examples:

* Text: **9 apr. 1410**  
  Annotation: [Type: Datum, Value: "9 apr. 1410"]



#### Label: Fundstelle

##### Beschreibung:
Verweise auf Dokumente oder Handschriften.

##### Standard Examples:

* Text: **L 138 254v**  
  Annotation: [Type: Fundstelle, Value: "L 138 254v."]



## Kommentare, unklare Fälle und Richtlinien zur ihrer Entscheidung

### Domic.
Im Abkürzungsverzeichnis des RG steht für domic. nur domicella/domicellus (Ritterfräulein, Stiftsdame; Knappe, Junker [kurialer Ehrentitel]), auch wenn man domicellarius (Domherr) erwarten würde.

### Doppeldeutige Begriffe
Manche Begriffe können in mehreren Kategorien fallen. Beispiel: „alt.“ kann für ein Objekt (Altar), als auch für ein kirchliches Amt (ein Altarist, also ein Priester, der Gottesdienste an diesem Altar abhält und dafür ein Einkommen erhält) stehen. Wir haben uns dazu entschieden, alt. als Objekt zu taggen. 
An dieser Stelle sollen weitere ambige Fälle gesammelt werden und unsere Entscheidungen festgehalten werden:
  - alt. = Objekt
  - par. eccl. = Institution
  - archidiac. = Kirchliches_Amt
  - vic. = Kirchliches_Amt

### Fit mentio
Fit mentio ("wird erwähnt") wird nicht getaggt.

### Klammern

Alle Angaben in Klammern, die eine Alternative darstellen, werden in den Tag ihres Bezugsausdruckes miteinbezogen, inkl. Klammern:  
- Henricus **de Gerpstede (Gherbstede)** -> Namenszusatz: de Gerpstede (Gherbstede)
- **Erhardus (Gerardus)** -> Vorname: Erhardus (Gerardus)
- **24 oct. 13 (20 sept. 1413)** -> Datum: 24 oct. 13 (20 sept. 1413)
- **056 148 (ASO 2 11).** -> Fundstelle: 056 148 (ASO 2 11).
- **Berpenick (Berporch)** -> Name_Ort: Berpenick (Berporch)
Bei “frei stehenden” Angaben in Klammern werden die Klammern ignoriert.  
- (**33,33 fl.**) -> Geldsumme: 33,33 fl.
- (procur. mag. Bruno Boghel) -> Kuriales_Amt: procur.; Akademischer_Grad: mag.; Vorname: Bruno; Namenszusatz: Boghel  

### Kombinationen aus mehreren Kategorien
Ein Eintrag, der mehrere Entitäten beschreibt, wird in entsprechende Einzelannotationen aufgeteilt.
  * Beispiel: Text: can. et preb. eccl. Sleswic.
    Annotation:
    - [Type: Kirchliches_Amt, Value: "can. et preb."]
    - [Type: Institution, Value: "eccl."]
    - [Type: Diözese, Value: "Sleswic."]

### Lect.
Bei der Abkürzung "lect." gibt es (wenigstens für das RG 3) noch Klärungsbedarf, weil es selten für Lektor und häufiger für einen Vermerk zum Geschäftsgang (lectio) zu stehen scheint. Wenn lect. am Ende des Regests steht, dann wird es nicht ausgezeichnet.

### maior und minor prebenda / ecclesia
Bei Fällen wie „incorp. maioris preb. eccl.“, bei denen nicht immer gleich klar ist, ob sich das Adjektiv maior/minor auf die Präbende oder die Kirche bezieht, wird es grundsätzlich gemeinsam mit preb. mit dem Tag „Kirchliches_Amt“ versehen (also nicht zu eccl. gezogen). 

### Ort vs. Diözese
- Steht nach der Angabe der Weihe (subdiac, diac., presb. , ep. etc.) der Name einer Stadt so muss diese als Diözese getaggt werden, weil Weihen auf Diözesen, nicht auf Städte erfolgen.
  - Beispiele: Henricus de Bocholdia al. d. Foet cler. Traiect.; ep. Vulterran. 
  - Achtung: Bei prepos. Plocen. wird Plocen. als Name_Ort, nicht als Diözese, getaggt.
- Die Ortsbezeichnungen nach e.m. (extra muros = außerhalb der Mauern von) werden immer als "Vorstadt" getaggt, z.B. e.m. Traiect.
- In Fällen wie “Prag. et Olumuc. dioc.” Ist davon auszugehen, dass das erste dioc. Weggefallen ist. Es werden also sowohl Prag. als auch Olumuc. als "Diözese" getaggt.
- Wenn marchio (Markgraf) vor Brandenburg. steht, wird Brandenburg. als "Herrschaftsgebiet" (nicht als Name_Ort oder Diözese) getaggt.

### Präpositionen

Die Präposition *de* wird nur beim Label Namenszusatz und Sozialer_Stand mitgetaggt: 
* Johannis **de Yselsteine** (de Yselsteine = Namenszusatz), Ghiselbertus de Lochorst **de nob. gen.** (de nob. gen. = Sozialer_Stand)    
In allen anderen Fällen wird nur der relevante Hauptbegriff annotiert, nicht die Präposition:  
* **de eccl.** (eccl. = "Institution"), **de locis interdictis** (locis interdictis = "de_loco_interdicto") etc.  

Entsprechendes gilt für weitere Präpositionen wie post ob. etc.

### Fundstelle
Für jede Quelle wird je ein Tag „Fundstelle“ vergeben, z.B. *C 1 4* (Fundstelle), *Ind. 323 127.* (Fundstelle)
Aber: *047 40 et 40v.* wird als eine Fundstelle getaggt.

### Thematische- / Topik-Tags
Wir haben uns aus zeitökonomischen Gründen dazu entschieden, keine thematischen Tags zu vergeben (z.B. „Geburtsdefekt“ für def. nat., „Interdikt“ für locis interdictis, „Ehe“ für matrim. usw.). Allerdings sollen die Nutzer/innen der fertigen Anwendung explizit darauf hingewiesen werden, dass sie bestimmte Themen, wie gewohnt, über die entsprechenden RG-Abkürzungen abrufen können. 
Beispielanfrage (falsch): Gib mir alle Ehefälle aus dem RG aus.
Beispielanfrage (richtig): Gib mir alle matrim. Fälle aus dem RG aus.

### Titelkirchen
Da die Namen derjenigen Kirchen, die Kardinalbischöfen, -priestern und -diakonen mit ihrer Ernennung zum Kardinal verliehen wurden, eine Mischform zwischen den Tags „Institution“, „Ort“ und „Patrozinium“ darstellen und ihre Anzahl zugleich finit ist, haben wir uns für einen eigenen Tag „Titelkirche“ entschieden. Man erkennt sie v.a. daran, dass in ihrer Nähe im Regest ein Kardinal genannt wird (ep. card., presb. card., diac. card.). In diesen Fällen wird ausnahmsweise darauf verzichtet, zusätzlich das Patrozinium oder den Ort als solche gesondert zu taggen. Beispiele: 
- presb. card. **tit. s. Laurentii in Damaso**
- diac. card. (tit.) **s. Georgii ad Velum Aureum**
- ep. **Portuen.** card.

### Ungünstige Trennung von zwei oder mehreren Wörtern
Manchmal kommt es vor, dass zwei Wörter, die eigentlich gemeinsam getaggt werden sollten (m. incorp.; ep. card.), durch andere Wörter getrennt werden (m. (Sigismundo Rom. Et Vng. rege) incorp.; ep. Portuen. card.). Behelfsmäßig haben wir jetzt beide Teile einzeln mit dem Tag Incorporatio bzw. KirchlichesAmt versehen - eine Lösung dafür muss noch gefunden werden, damit die Zuordnung eindeutig und konsistent ist (z.B. Pfeilverbindungen in Inception, die anzeigen, dass zwei Wörter zusammen unter ein Tag gehören).(?)