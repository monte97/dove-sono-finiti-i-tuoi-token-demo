# Uscite del banco del 5/11 con le misure corrette

Prodotte dal commit `45f799d` (ramo `rami-paralleli`) sulle registrazioni di `registrazioni/`, senza modificarle e senza chiamare l'API. I comandi allora erano `strati.py --misure N` e simili; qui sono scritti con la CLI di oggi (`strati misure N`), che dà la stessa uscita. Ogni blocco e' l'uscita del comando scritto sopra, senza ritocchi salvo togliere i codici colore del terminale. `strati misure N` legge tutte le cartelle `strato-N*`: `strati misure 5` comprende anche le tre correzioni (`strato-5-correzione`, `-completa`, `-dialogo`). Gli schemi sono rientrati di quattro spazi per non far interpretare il blocco Mermaid.

## `strati riepilogo`

```
cartella                     modo     n trace span attr chiam. giuste avvis. sbagl. email sec med token med     $ med
strato-0                     guasto  30     0    0    0     19      2      4     24     0    18.7     49461  0.005897
strato-0                     sana    30     0    0    0     19     30      0      0     0    20.0     19630  0.002787
strato-1                     guasto  30    20   20  526     20      0      7     23     0    20.7     51092  0.006206
strato-1                     sana    30    20   20  540     20     30      0      0     0    20.7     20921  0.002994
strato-2                     guasto  30     1   35  588     19      0      7     23     0    21.1     49393  0.005878
strato-2                     sana    30     1   35  588     19     30      0      0     0    19.1     19774  0.002750
strato-3                     guasto  30     1   44  674     20      2      7     21     0    22.2     51874  0.006403
strato-3                     sana    30     1   42  654     20     30      0      0     0    21.0     20759  0.002936
strato-4                     guasto  30     1   45  707     20      2      5     23     0    21.3     50549  0.006119
strato-4                     sana    30     1   43  682     20     30      0      0     0    21.2     21218  0.003023
strato-5                     guasto  30     1   45  768     20      0      8     22     3    21.2     50806  0.006063
strato-5                     sana    30     1   41  707     19     30      0      0     3    19.5     20058  0.002835
strato-5-correzione          guasto  30     1   48  824     22      5     25      0     4    31.2     65491  0.008392
strato-5-correzione-completa guasto  30     1   46  809     22      2     28      0     4    29.3     23758  0.003908
strato-5-correzione-dialogo  guasto  30     1   72 1234     33      2     28      0     3    37.7     66819  0.009160

speso in tutto, dalle registrazioni: $ 2.2118
```

## `strati misure 0`

```
 strato-0 
guasto: n 30 · giusta 2 · avvisata 4 · sbagliata 24
  programma, sale, avvisi nello stesso giro            serve lo strato 2
  avvisi chiamato dopo che si sapeva la sala           serve lo strato 2
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi               serve lo strato 2
  valida richiede ad avvisi                            serve lo strato 2
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          serve lo strato 2
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente                                     serve lo strato 2
  guardia dei cicli scattata                           serve lo strato 2
  mediane: profondità 0 · span 0 · chiamate al modello 19 · token 49461 · secondi 18.7 · $ 0.005897
  forme dell'albero                                    serve lo strato 2
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro            serve lo strato 2
  avvisi chiamato dopo che si sapeva la sala           serve lo strato 2
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi               serve lo strato 2
  valida richiede ad avvisi                            serve lo strato 2
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          serve lo strato 2
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente                                     serve lo strato 2
  guardia dei cicli scattata                           serve lo strato 2
  mediane: profondità 0 · span 0 · chiamate al modello 19 · token 19630 · secondi 20.0 · $ 0.002787
  forme dell'albero                                    serve lo strato 2

```

## `strati misure 1`

```
 strato-1 
guasto: n 30 · giusta 0 · avvisata 7 · sbagliata 23
  programma, sale, avvisi nello stesso giro            serve lo strato 2
  avvisi chiamato dopo che si sapeva la sala           serve lo strato 2
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi               serve lo strato 2
  valida richiede ad avvisi                            serve lo strato 2
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          serve lo strato 2
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente                                     serve lo strato 2
  guardia dei cicli scattata                           serve lo strato 2
  mediane: profondità 1 · span 20 · chiamate al modello 20 · token 51092 · secondi 20.7 · $ 0.006206
  forme dell'albero                                    serve lo strato 2
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro            serve lo strato 2
  avvisi chiamato dopo che si sapeva la sala           serve lo strato 2
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi               serve lo strato 2
  valida richiede ad avvisi                            serve lo strato 2
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          serve lo strato 2
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente                                     serve lo strato 2
  guardia dei cicli scattata                           serve lo strato 2
  mediane: profondità 1 · span 20 · chiamate al modello 20 · token 20921 · secondi 20.7 · $ 0.002994
  forme dell'albero                                    serve lo strato 2

```

## `strati misure 2`

```
 strato-2 
guasto: n 30 · giusta 0 · avvisata 7 · sbagliata 23
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            4 su 30
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi                8 su 30
  valida richiede ad avvisi                            20 su 30
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          22 su 30
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente (mediana)                           avvisi 34424 · coordina 4829 · programma 5403 · sale 2958 · valida 2465
  costo per agente, $ (mediana)                        avvisi 0.003737 · coordina 0.000709 · programma 0.000767 · sale 0.000455 · valida 0.000353
  quota di avvisi sui token della richiesta            mediana 67%
  quota delle riletture (token in ingresso)            mediana 19%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 63
  mediane: profondità 9 · span 35 · chiamate al modello 19 · token 49393 · secondi 21.1 · $ 0.005878
  18 forme dell'albero:
     8 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida({avvisi,programma(sale)})
     3 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida({avvisi,programma(sale sale)})
     2 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida
     2 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida(programma(sale))
     1 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida({avvisi,programma(sale sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale sale),sale} coordina>valida
     1 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida({avvisi,programma(sale sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale sale),sale} coordina>valida({avvisi,programma(sale)}) coordina>avvisi
     1 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida({avvisi,programma(sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida(programma(sale))
     1 × codice>coordina coordina>{avvisi,programma(sale)} coordina>sale coordina>sale coordina>valida
     1 × codice>coordina coordina>programma(sale) coordina>valida({avvisi,programma(sale sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida({avvisi,programma(sale)})
     1 × codice>coordina coordina>programma(sale) coordina>valida({avvisi,programma(sale sale)}) coordina>{avvisi,sale}
     1 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida({avvisi,programma(sale)}) coordina>avvisi
     1 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida({avvisi,programma(sale sale)}) coordina>avvisi coordina>valida({avvisi,programma(sale)})
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            0 su 30
  la richiesta ad avvisi nomina la sala B              serve lo strato 3
  leggi_avvisi ha restituito l'avviso sulla sala B     serve lo strato 3
  avvisi lo riporta a coordina                         serve lo strato 3
  sale chiamato da due chiamanti diversi               10 su 30
  valida richiede ad avvisi                            20 su 30
  ...e la risposta di avvisi riporta l'avviso          serve lo strato 3
  valida richiede a programma                          20 su 30
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       serve lo strato 3
  l'email arriva a valida                              serve lo strato 3
  token per agente (mediana)                           avvisi 4922 · coordina 4802 · programma 5288 · sale 3004 · valida 2463
  costo per agente, $ (mediana)                        avvisi 0.000640 · coordina 0.000707 · programma 0.000741 · sale 0.000457 · valida 0.000356
  quota di avvisi sui token della richiesta            mediana 22%
  quota delle riletture (token in ingresso)            mediana 47%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 50
  mediane: profondità 9 · span 35 · chiamate al modello 19 · token 19774 · secondi 19.1 · $ 0.002750
  12 forme dell'albero:
     6 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida({avvisi,programma(sale)})
     5 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida({avvisi,programma(sale)})
     4 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida({avvisi,programma(sale sale)})
     4 × codice>coordina coordina>{avvisi,programma(sale)} coordina>valida
     3 × codice>coordina coordina>{avvisi,programma(sale sale),sale} coordina>valida
     2 × codice>coordina coordina>{avvisi,programma(sale)} coordina>sale coordina>sale coordina>valida({avvisi,programma(sale sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi,programma(sale)} coordina>sale coordina>sale coordina>valida({avvisi,programma(sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida({avvisi,programma(sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida
     1 × codice>coordina coordina>{avvisi,programma(sale),sale} coordina>valida({avvisi,programma(sale sale)})
     1 × codice>coordina coordina>{avvisi,programma(sale)} coordina>sale coordina>sale coordina>valida

```

## `strati misure 3`

```
 strato-3 
guasto: n 30 · giusta 2 · avvisata 7 · sbagliata 21
  programma, sale, avvisi nello stesso giro             4 su 30
  avvisi chiamato dopo che si sapeva la sala            3 su 30
  la richiesta ad avvisi nomina la sala B               3 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                          9 su 30
  sale chiamato da due chiamanti diversi                6 su 30
  valida richiede ad avvisi                            21 su 30
  ...e la risposta di avvisi riporta l'avviso           9 su 30
  valida richiede a programma                          22 su 30
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       23 su 30 · mai chiamata in 0
  l'email arriva a valida                               1 su 30
  token per agente (mediana)                           avvisi 34570 · coordina 4996 · programma 5478 · sale 2938 · valida 2530
  costo per agente, $ (mediana)                        avvisi 0.003810 · coordina 0.000739 · programma 0.000779 · sale 0.000434 · valida 0.000390
  quota di avvisi sui token della richiesta            mediana 65%
  quota delle riletture (token in ingresso)            mediana 19%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 68
  mediane: profondità 9 · span 44 · chiamate al modello 20 · token 51874 · secondi 22.2 · $ 0.006403
  19 forme dell'albero:
     4 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))}) coordina>avvisi(leggi_avvisi)
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>sale coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>{avvisi(leggi_avvisi),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            0 su 30
  la richiesta ad avvisi nomina la sala B               0 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B      0 su 30
  avvisi lo riporta a coordina                          0 su 30
  sale chiamato da due chiamanti diversi                8 su 30
  valida richiede ad avvisi                            20 su 30
  ...e la risposta di avvisi riporta l'avviso           0 su 30
  valida richiede a programma                          21 su 30
  pagine di avvisi lette                               serve lo strato 4
  valida approva                                       30 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 4896 · coordina 4796 · programma 5402 · sale 3059 · valida 2463
  costo per agente, $ (mediana)                        avvisi 0.000638 · coordina 0.000698 · programma 0.000768 · sale 0.000485 · valida 0.000347
  quota di avvisi sui token della richiesta            mediana 21%
  quota delle riletture (token in ingresso)            mediana 48%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 53
  mediane: profondità 9 · span 42 · chiamate al modello 20 · token 20759 · secondi 21.0 · $ 0.002936
  16 forme dell'albero:
     6 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     4 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     4 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>sale(leggi_sale) coordina>sale(leggi_sale) coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale})),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale) coordina>sale(leggi_sale) coordina>valida

```

## `strati misure 4`

```
 strato-4 
guasto: n 30 · giusta 2 · avvisata 5 · sbagliata 23
  programma, sale, avvisi nello stesso giro             7 su 30
  avvisi chiamato dopo che si sapeva la sala            3 su 30
  la richiesta ad avvisi nomina la sala B               3 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                          7 su 30
  sale chiamato da due chiamanti diversi               10 su 30
  valida richiede ad avvisi                            20 su 30
  ...e la risposta di avvisi riporta l'avviso           7 su 30
  valida richiede a programma                          21 su 30
  pagine di avvisi lette da coordina                   mediana 40 (da 40 a 80)
  pagine di avvisi nei ricontrolli                     mediana 40 (da 0 a 40)
  valida approva                                       23 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 34502 · coordina 4812 · programma 5272 · sale 3116 · valida 2476
  costo per agente, $ (mediana)                        avvisi 0.003776 · coordina 0.000711 · programma 0.000735 · sale 0.000503 · valida 0.000357
  quota di avvisi sui token della richiesta            mediana 65%
  quota delle riletture (token in ingresso)            mediana 19%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 56
  mediane: profondità 9 · span 45 · chiamate al modello 20 · token 50549 · secondi 21.3 · $ 0.006119
  19 forme dell'albero:
     5 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>avvisi(leggi_avvisi)
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>{sale(leggi_sale),valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})}
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))}) coordina>avvisi(leggi_avvisi)
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))} coordina>valida(programma(leggi_programma sale(leggi_sale) sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))}) coordina>avvisi(leggi_avvisi)
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            0 su 30
  la richiesta ad avvisi nomina la sala B               0 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B      0 su 30
  avvisi lo riporta a coordina                          0 su 30
  sale chiamato da due chiamanti diversi                7 su 30
  valida richiede ad avvisi                            17 su 30
  ...e la risposta di avvisi riporta l'avviso           0 su 30
  valida richiede a programma                          21 su 30
  pagine di avvisi lette da coordina                   mediana 3 (da 3 a 3)
  pagine di avvisi nei ricontrolli                     mediana 3 (da 0 a 3)
  valida approva                                       30 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 4878 · coordina 4800 · programma 5658 · sale 3138 · valida 2464
  costo per agente, $ (mediana)                        avvisi 0.000629 · coordina 0.000706 · programma 0.000819 · sale 0.000515 · valida 0.000355
  quota di avvisi sui token della richiesta            mediana 20%
  quota delle riletture (token in ingresso)            mediana 48%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 51
  mediane: profondità 9 · span 43 · chiamate al modello 20 · token 21218 · secondi 21.2 · $ 0.003023
  24 forme dell'albero:
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale})),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida(programma(leggi_programma sale(leggi_sale) sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida(programma(leggi_programma sale sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>sale(leggi_sale) coordina>sale(leggi_sale) coordina>valida

```

## `strati misure 5`

```
 strato-5 
guasto: n 30 · giusta 0 · avvisata 8 · sbagliata 22
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            1 su 30
  la richiesta ad avvisi nomina la sala B               1 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                          7 su 30
  sale chiamato da due chiamanti diversi               10 su 30
  valida richiede ad avvisi                            19 su 30
  ...e la risposta di avvisi riporta l'avviso           7 su 30
  valida richiede a programma                          19 su 30
  pagine di avvisi lette da coordina                   mediana 40 (da 40 a 80)
  pagine di avvisi nei ricontrolli                     mediana 40 (da 0 a 40)
  valida approva                                       22 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 34478 · coordina 4850 · programma 5287 · sale 2968 · valida 2461
  costo per agente, $ (mediana)                        avvisi 0.003760 · coordina 0.000720 · programma 0.000741 · sale 0.000442 · valida 0.000358
  quota di avvisi sui token della richiesta            mediana 64%
  quota delle riletture (token in ingresso)            mediana 20%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 53
  mediane: profondità 9 · span 45 · chiamate al modello 20 · token 50806 · secondi 21.2 · $ 0.006063
  17 forme dell'albero:
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale) coordina>sale(leggi_sale) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>sale coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>{sale,valida(programma(leggi_programma sale sale(leggi_sale)))}
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>avvisi(leggi_avvisi)
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida(avvisi(leggi_avvisi))
sana: n 30 · giusta 30 · avvisata 0 · sbagliata 0
  programma, sale, avvisi nello stesso giro             6 su 30
  avvisi chiamato dopo che si sapeva la sala            0 su 30
  la richiesta ad avvisi nomina la sala B               0 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B      0 su 30
  avvisi lo riporta a coordina                          0 su 30
  sale chiamato da due chiamanti diversi                6 su 30
  valida richiede ad avvisi                            22 su 30
  ...e la risposta di avvisi riporta l'avviso           0 su 30
  valida richiede a programma                          25 su 30
  pagine di avvisi lette da coordina                   mediana 3 (da 3 a 6)
  pagine di avvisi nei ricontrolli                     mediana 3 (da 0 a 6)
  valida approva                                       30 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 4927 · coordina 4732 · programma 5573 · sale 2978 · valida 2476
  costo per agente, $ (mediana)                        avvisi 0.000653 · coordina 0.000689 · programma 0.000809 · sale 0.000448 · valida 0.000361
  quota di avvisi sui token della richiesta            mediana 22%
  quota delle riletture (token in ingresso)            mediana 47%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 49
  mediane: profondità 9 · span 41 · chiamate al modello 19 · token 20058 · secondi 19.5 · $ 0.002835
  15 forme dell'albero:
     8 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     4 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida(programma(leggi_programma sale(leggi_sale)))
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale)),sale(leggi_sale)} coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})

 strato-5-correzione 
guasto: n 30 · giusta 5 · avvisata 25 · sbagliata 0
  programma, sale, avvisi nello stesso giro             0 su 30
  avvisi chiamato dopo che si sapeva la sala           30 su 30
  la richiesta ad avvisi nomina la sala B              30 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                         30 su 30
  sale chiamato da due chiamanti diversi                2 su 30
  valida richiede ad avvisi                            28 su 30
  ...e la risposta di avvisi riporta l'avviso          28 su 30
  valida richiede a programma                          27 su 30
  pagine di avvisi lette da coordina                   mediana 80 (da 40 a 120)
  pagine di avvisi nei ricontrolli                     mediana 40 (da 0 a 40)
  valida approva                                        3 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 43467 · coordina 7606 · programma 5602 · sale 2984 · valida 3940
  costo per agente, $ (mediana)                        avvisi 0.004865 · coordina 0.001157 · programma 0.000814 · sale 0.000443 · valida 0.000884
  quota di avvisi sui token della richiesta            mediana 69%
  quota delle riletture (token in ingresso)            mediana 17%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 63
  mediane: profondità 9 · span 48 · chiamate al modello 22 · token 65491 · secondi 31.2 · $ 0.008392
  19 forme dell'albero:
     5 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     4 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     3 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale)),programma(sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida(avvisi(leggi_avvisi))
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>sale(leggi_sale)
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>{avvisi(leggi_avvisi),sale(leggi_sale)} coordina>sale(leggi_sale) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale})) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})

 strato-5-correzione-completa 
guasto: n 30 · giusta 2 · avvisata 28 · sbagliata 0
  programma, sale, avvisi nello stesso giro             0 su 30
  avvisi chiamato dopo che si sapeva la sala           25 su 30
  la richiesta ad avvisi nomina la sala B              25 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                         30 su 30
  sale chiamato da due chiamanti diversi                2 su 30
  valida richiede ad avvisi                            28 su 30
  ...e la risposta di avvisi riporta l'avviso          28 su 30
  valida richiede a programma                          28 su 30
  pagine di avvisi lette da coordina                   mediana 1 (da 1 a 4)
  pagine di avvisi nei ricontrolli                     mediana 1 (da 0 a 1)
  valida approva                                        1 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 3595 · coordina 7358 · programma 5614 · sale 2662 · valida 3777
  costo per agente, $ (mediana)                        avvisi 0.000667 · coordina 0.001120 · programma 0.000818 · sale 0.000390 · valida 0.000819
  quota di avvisi sui token della richiesta            mediana 16%
  quota delle riletture (token in ingresso)            mediana 53%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 9 (agenti uno dentro l'altro 3) · span 60
  mediane: profondità 9 · span 46 · chiamate al modello 22 · token 23758 · secondi 29.3 · $ 0.003908
  20 forme dell'albero:
     5 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi,programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi,programma({leggi_programma,sale(leggi_sale)})} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale})) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>programma({leggi_programma,sale(leggi_sale)}) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi,programma(leggi_programma sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>programma(leggi_programma sale sale(leggi_sale)) coordina>{avvisi(leggi_avvisi),sale(leggi_sale)} coordina>{sale(leggi_sale),valida({avvisi(leggi_avvisi),programma(leggi_programma sale sale(leggi_sale))})}
     1 × codice>coordina coordina>programma(leggi_programma sale(leggi_sale)) coordina>avvisi(leggi_avvisi) coordina>valida({avvisi(leggi_avvisi),programma({leggi_programma,sale(leggi_sale)})})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,leggi_avvisi,leggi_avvisi}),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))} coordina>valida({avvisi(leggi_avvisi),programma(leggi_programma sale(leggi_sale))}) coordina>sale(leggi_sale)
     1 × codice>coordina coordina>{avvisi,programma(leggi_programma sale sale(leggi_sale))} coordina>avvisi(leggi_avvisi) coordina>valida

 strato-5-correzione-dialogo 
guasto: n 30 · giusta 2 · avvisata 28 · sbagliata 0
  programma, sale, avvisi nello stesso giro            10 su 30
  avvisi chiamato dopo che si sapeva la sala            0 su 30
  la richiesta ad avvisi nomina la sala B               0 su 30
  leggi_avvisi ha restituito l'avviso sulla sala B     30 su 30
  avvisi lo riporta a coordina                         30 su 30
  sale chiamato da due chiamanti diversi               13 su 30
  valida richiede ad avvisi                            29 su 30
  ...e la risposta di avvisi riporta l'avviso          29 su 30
  valida richiede a programma                          29 su 30
  avvisi chiede a programma                            30 su 30
  ...e poi avvisi riporta l'avviso                     30 su 30
  pagine di avvisi lette da coordina                   mediana 40 (da 40 a 40)
  pagine di avvisi nei ricontrolli                     mediana 40 (da 0 a 40)
  valida approva                                        2 su 30 · mai chiamata in 0
  l'email arriva a valida                               0 su 30
  token per agente (mediana)                           avvisi 36624 · coordina 6238 · programma 11865 · sale 6630 · valida 3986
  costo per agente, $ (mediana)                        avvisi 0.004292 · coordina 0.001012 · programma 0.001749 · sale 0.000989 · valida 0.000866
  quota di avvisi sui token della richiesta            mediana 56%
  quota delle riletture (token in ingresso)            mediana 25%
  guardia dei cicli scattata                            0 su 30 · 0 volte · guardia mai scattata
  massimi: profondità 11 (agenti uno dentro l'altro 4) · span 86
  mediane: profondità 11 · span 72 · chiamate al modello 33 · token 66819 · secondi 37.7 · $ 0.009160
  28 forme dell'albero:
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma(leggi_programma sale(leggi_sale))})
     2 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)} sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi programma({leggi_programma,sale(leggi_sale)})),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}) coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma({leggi_programma,sale(leggi_sale)})})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale})}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma({leggi_programma,sale(leggi_sale)})} coordina>valida
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale) coordina>valida({avvisi(leggi_avvisi programma(leggi_programma sale(leggi_sale))),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi programma(leggi_programma sale sale(leggi_sale))),programma({leggi_programma,sale(leggi_sale)})})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi(leggi_avvisi programma(leggi_programma sale(leggi_sale))),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi(leggi_avvisi programma(leggi_programma sale sale(leggi_sale))),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>sale(leggi_sale) coordina>sale(leggi_sale) coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma({leggi_programma,sale(leggi_sale)})} coordina>valida({avvisi(leggi_avvisi programma(leggi_programma sale sale(leggi_sale))),programma(leggi_programma sale(leggi_sale) sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)})}),programma(leggi_programma sale sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma({leggi_programma,sale(leggi_sale)})} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale) sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale} sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale sale(leggi_sale))} coordina>valida({avvisi({leggi_avvisi,programma(leggi_programma sale sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale {leggi_sale,leggi_sale,leggi_sale}))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi({leggi_avvisi,programma({leggi_programma,sale(leggi_sale)} sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale))})
     1 × codice>coordina coordina>{avvisi({leggi_avvisi,programma(leggi_programma sale(leggi_sale))}),programma(leggi_programma sale(leggi_sale)),sale(leggi_sale)} coordina>valida({avvisi(leggi_avvisi programma(leggi_programma sale(leggi_sale))),programma(leggi_programma sale(leggi_sale))})

```

## `strati segnali`

```
strato-0 · guasto · 30 richieste
  forme dell'albero  — serve lo strato 2
  valida approva     — serve lo strato 3
  costo a richiesta  — serve lo strato 1
  quota di avvisi    — serve lo strato 2
  pagine di avvisi   — serve lo strato 4

strato-0 · sana · 30 richieste
  forme dell'albero  — serve lo strato 2
  valida approva     — serve lo strato 3
  costo a richiesta  — serve lo strato 1
  quota di avvisi    — serve lo strato 2
  pagine di avvisi   — serve lo strato 4

strato-1 · guasto · 30 richieste
  forme dell'albero  — serve lo strato 2
  valida approva     — serve lo strato 3
  costo a richiesta  mediana $ 0.006206 · 95° percentile $ 0.009260
  quota di avvisi    — serve lo strato 2
  pagine di avvisi   — serve lo strato 4

strato-1 · sana · 30 richieste
  forme dell'albero  — serve lo strato 2
  valida approva     — serve lo strato 3
  costo a richiesta  mediana $ 0.002994 · 95° percentile $ 0.003811
  quota di avvisi    — serve lo strato 2
  pagine di avvisi   — serve lo strato 4

strato-2 · guasto · 30 richieste
  forme dell'albero  18 (la più frequente in 8 run)
  valida approva     — serve lo strato 3
  costo a richiesta  mediana $ 0.005878 · 95° percentile $ 0.009626
  quota di avvisi    mediana 67% dei token · 95° percentile 71%
  pagine di avvisi   — serve lo strato 4

strato-2 · sana · 30 richieste
  forme dell'albero  12 (la più frequente in 6 run)
  valida approva     — serve lo strato 3
  costo a richiesta  mediana $ 0.002750 · 95° percentile $ 0.004232
  quota di avvisi    mediana 22% dei token · 95° percentile 25%
  pagine di avvisi   — serve lo strato 4

strato-3 · guasto · 30 richieste
  forme dell'albero  19 (la più frequente in 4 run)
  valida approva     23 su 32 verdetti
  costo a richiesta  mediana $ 0.006403 · 95° percentile $ 0.010526
  quota di avvisi    mediana 65% dei token · 95° percentile 75%
  pagine di avvisi   — serve lo strato 4

strato-3 · sana · 30 richieste
  forme dell'albero  16 (la più frequente in 6 run)
  valida approva     30 su 30 verdetti
  costo a richiesta  mediana $ 0.002936 · 95° percentile $ 0.003520
  quota di avvisi    mediana 21% dei token · 95° percentile 25%
  pagine di avvisi   — serve lo strato 4

strato-4 · guasto · 30 richieste
  forme dell'albero  19 (la più frequente in 5 run)
  valida approva     23 su 30 verdetti
  costo a richiesta  mediana $ 0.006119 · 95° percentile $ 0.009137
  quota di avvisi    mediana 65% dei token · 95° percentile 72%
  pagine di avvisi   mediana 40 · massimo 80

strato-4 · sana · 30 richieste
  forme dell'albero  24 (la più frequente in 3 run)
  valida approva     30 su 30 verdetti
  costo a richiesta  mediana $ 0.003023 · 95° percentile $ 0.003514
  quota di avvisi    mediana 20% dei token · 95° percentile 25%
  pagine di avvisi   mediana 3 · massimo 3

strato-5 · guasto · 30 richieste
  forme dell'albero  17 (la più frequente in 3 run)
  valida approva     22 su 30 verdetti
  costo a richiesta  mediana $ 0.006063 · 95° percentile $ 0.007933
  quota di avvisi    mediana 64% dei token · 95° percentile 70%
  pagine di avvisi   mediana 40 · massimo 80

strato-5 · sana · 30 richieste
  forme dell'albero  15 (la più frequente in 8 run)
  valida approva     30 su 30 verdetti
  costo a richiesta  mediana $ 0.002835 · 95° percentile $ 0.003529
  quota di avvisi    mediana 22% dei token · 95° percentile 26%
  pagine di avvisi   mediana 3 · massimo 6

strato-5-correzione · guasto · 30 richieste
  forme dell'albero  19 (la più frequente in 5 run)
  valida approva     3 su 30 verdetti
  costo a richiesta  mediana $ 0.008392 · 95° percentile $ 0.010489
  quota di avvisi    mediana 69% dei token · 95° percentile 74%
  pagine di avvisi   mediana 80 · massimo 120

strato-5-correzione-completa · guasto · 30 richieste
  forme dell'albero  20 (la più frequente in 5 run)
  valida approva     1 su 30 verdetti
  costo a richiesta  mediana $ 0.003908 · 95° percentile $ 0.004990
  quota di avvisi    mediana 16% dei token · 95° percentile 23%
  pagine di avvisi   mediana 1 · massimo 4

strato-5-correzione-dialogo · guasto · 30 richieste
  forme dell'albero  28 (la più frequente in 2 run)
  valida approva     2 su 30 verdetti
  costo a richiesta  mediana $ 0.009160 · 95° percentile $ 0.010745
  quota di avvisi    mediana 56% dei token · 95° percentile 68%
  pagine di avvisi   mediana 40 · massimo 40

```

## `strati schema registrazioni/strato-5 --modo guasto`

    schema del sistema: 30 run, strato 5
    
    chi chiama chi (in quante run · volte in totale)
       utente → coordina             30 su 30 ·  30 volte
       coordina → programma          30 su 30 ·  30 volte
      *coordina → sale               10 su 30 ·  12 volte
       coordina → avvisi             30 su 30 ·  31 volte
       coordina → valida             30 su 30 ·  30 volte
       programma → sale              30 su 30 ·  67 volte
      *valida → programma            19 su 30 ·  19 volte
      *valida → avvisi               19 su 30 ·  19 volte
      strumenti dei dati
         programma → leggi_programma   30 su 30 ·  49 volte
         sale → leggi_sale             30 su 30 ·  67 volte
         avvisi → leggi_avvisi         30 su 30 ·  50 volte
    
    rimpalli (* nell'elenco sopra)
      programma chiamato da 2 chiamanti (coordina, valida): 19 run su 30
      sale chiamato da 2 chiamanti (coordina, programma): 10 run su 30
      avvisi chiamato da 2 chiamanti (coordina, valida): 19 run su 30
      valida richiama avvisi: 19 run su 30
        ...e la risposta riporta l'avviso sulla sala B: 7 run su 30
      valida richiama programma: 19 run su 30
      avvisi chiede a programma (dialogo): 0 run su 30
      guardia dei cicli scattata: 0 run su 30 · 0 volte
    
    ```mermaid
    flowchart LR
      %% legenda: ogni arco e' «in quante run su quante» (×N = volte per run, in media);
      %% tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che chiede a programma, arco respinto dalla guardia); rosso = coordina → sale quando sale e' chiamato anche da programma
      utente([utente])
      coordina[coordina]
      programma[programma]
      sale[sale]
      avvisi[avvisi]
      valida[valida]
      utente -->|30/30| coordina
      coordina -->|30/30| programma
      coordina -->|10/30 ×1.2| sale
      coordina -->|30/30| avvisi
      coordina -->|30/30| valida
      programma -->|30/30 ×2.2| sale
      valida -.->|19/30| programma
      valida -.->|19/30| avvisi
      linkStyle 6,7 stroke:#7f8c8d,stroke-width:2px,color:#7f8c8d
      linkStyle 2 stroke:#c0392b,stroke-width:3px,color:#c0392b
    ```

## `strati schema registrazioni/strato-5-correzione-dialogo --modo guasto`

    schema del sistema: 30 run, strato 5
    
    chi chiama chi (in quante run · volte in totale)
       utente → coordina             30 su 30 ·  30 volte
       coordina → programma          30 su 30 ·  30 volte
      *coordina → sale               13 su 30 ·  14 volte
       coordina → avvisi             30 su 30 ·  30 volte
       coordina → valida             30 su 30 ·  30 volte
       programma → sale              30 su 30 · 158 volte
      *avvisi → programma            30 su 30 ·  59 volte
      *valida → programma            29 su 30 ·  29 volte
      *valida → avvisi               29 su 30 ·  29 volte
      strumenti dei dati
         programma → leggi_programma   30 su 30 · 118 volte
         sale → leggi_sale             30 su 30 · 145 volte
         avvisi → leggi_avvisi         30 su 30 ·  59 volte
    
    rimpalli (* nell'elenco sopra)
      programma chiamato da 3 chiamanti (coordina, avvisi, valida): 30 run su 30
      sale chiamato da 2 chiamanti (coordina, programma): 13 run su 30
      avvisi chiamato da 2 chiamanti (coordina, valida): 29 run su 30
      valida richiama avvisi: 29 run su 30
        ...e la risposta riporta l'avviso sulla sala B: 29 run su 30
      valida richiama programma: 29 run su 30
      avvisi chiede a programma (dialogo): 30 run su 30
      guardia dei cicli scattata: 0 run su 30 · 0 volte
    
    ```mermaid
    flowchart LR
      %% legenda: ogni arco e' «in quante run su quante» (×N = volte per run, in media);
      %% tratteggiato = chi controlla o chiede a una fonte fuori dal giro di coordina (valida che richiama, avvisi che chiede a programma, arco respinto dalla guardia); rosso = coordina → sale quando sale e' chiamato anche da programma
      utente([utente])
      coordina[coordina]
      programma[programma]
      sale[sale]
      avvisi[avvisi]
      valida[valida]
      utente -->|30/30| coordina
      coordina -->|30/30| programma
      coordina -->|13/30 ×1.1| sale
      coordina -->|30/30| avvisi
      coordina -->|30/30| valida
      programma -->|30/30 ×5.3| sale
      avvisi -.->|30/30 ×2.0| programma
      valida -.->|29/30| programma
      valida -.->|29/30| avvisi
      linkStyle 6,7,8 stroke:#7f8c8d,stroke-width:2px,color:#7f8c8d
      linkStyle 2 stroke:#c0392b,stroke-width:3px,color:#c0392b
    ```

