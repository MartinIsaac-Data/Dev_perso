# Notebooks — impasse volontaire

Les notebooks servent à **explorer**. Aucun module de `spp/` n'importe quoi
que ce soit d'ici, et la CI le vérifie.

Dès qu'une idée est retenue, elle est réimplémentée dans `spp/` avec des
tests. C'est la seule façon d'éviter le classique « le modèle de production
est un notebook exporté » — dont la conséquence habituelle est un
training/serving skew invisible (voir ADR-0003).
