# Contrôle automatisé des paiements – Démonstrateur audit & IA

Mini-application de contrôle interne sur données fictives : import CSV, huit familles de tests déterministes, cotation des risques, recommandations, synthèse et exports. L’IA ne décide jamais d’une anomalie ; elle peut uniquement reformuler les constats produits par les règles.

## Lancer

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\streamlit run app.py
```

Le jeu `data/paiements_demo.csv` est chargé par défaut. Le modèle CSV téléchargeable dans le panneau gauche donne les colonnes attendues. Le bouton « Télécharger les données analysées » fournit le fichier source complet correspondant au contrôle affiché. Un fichier importé remplace le jeu fictif, est validé, puis relance immédiatement tous les contrôles. Le rapport Excel contient les constats, le montant total contrôlé et un onglet de traçabilité avec les paiements sources.

Optionnel : définir `OPENAI_API_KEY` pour activer la rédaction générative et `OPENAI_MODEL` pour choisir le modèle. Sans clé, une synthèse locale transparente maintient l’application pleinement fonctionnelle.

> Démonstrateur fictif sans lien avec une entreprise cliente non identifiée. Les seuils sont illustratifs et doivent être adaptés aux procédures réelles.
