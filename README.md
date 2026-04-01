# Registre numerique des fiches qualite

Application web en ligne pour centraliser la numerotation des fiches qualite, suivre leur statut et controler les acces utilisateurs.

## Fonctionnalites

- Numerotation automatique au format `QT230201-GSS-QA-ITN-014171` a `QT230201-GSS-QA-ITN-014179`
- Prefixe global par defaut : `QT230201-GSS-QA-ITN-01417`
- Base PostgreSQL pour la production
- Mode SQLite conserve pour le developpement local rapide
- Connexion utilisateur avec session securisee par cookie HTTP
- Roles `admin`, `editor` et `viewer`
- Creation, modification et suppression des fiches selon les droits
- Recherche, filtres, tableau de bord et export CSV
- Panneau administrateur pour ajouter de nouveaux utilisateurs
- Reinitialisation admin des mots de passe avec mot de passe temporaire
- Changement du mot de passe par l'utilisateur connecte
- Trace des creations et mises a jour par utilisateur

## Comptes

Au premier lancement, un compte administrateur est cree automatiquement.

- utilisateur : `admin`
- mot de passe : `admin1234`

Pour un usage reel, changez ces valeurs avant le premier demarrage avec les variables d'environnement suivantes :

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_NAME`

## Lancement local

1. Ouvrir un terminal dans le dossier du projet
2. Lancer `python server.py`
3. Ouvrir `http://127.0.0.1:8765`

Variables disponibles :

- `HOST` : adresse d'ecoute du serveur
- `PORT` : port HTTP
- `DATABASE_URL` : URL PostgreSQL de production, par exemple `postgresql://user:password@host:5432/dbname`
- `ADMIN_USERNAME` : nom du premier administrateur
- `ADMIN_PASSWORD` : mot de passe du premier administrateur
- `ADMIN_NAME` : nom affiche du premier administrateur
- `DB_PATH` : chemin du fichier SQLite
- `COOKIE_SECURE` : mettre `true` derriere HTTPS

Si `DATABASE_URL` est defini, l'application utilise PostgreSQL. Sinon elle utilise SQLite en local.

## Mot de passe oublie

Deux solutions sont disponibles :

1. Depuis l'application :
   un administrateur peut reinitialiser le mot de passe d'un utilisateur depuis le panneau `Utilisateurs et acces`.
   L'application genere alors un mot de passe temporaire que l'utilisateur devra changer apres connexion.

2. Depuis le terminal, si plus aucun admin ne peut entrer :
   `python server.py --reset-user-password admin --new-password NouveauMotDePasse123`

Vous pouvez remplacer `admin` par n'importe quel nom d'utilisateur existant.

En mode local, la base `quality_sheets.db` est creee automatiquement au premier lancement.

## Structure

- `server.py` : serveur HTTP, API JSON, authentification, sessions, SQLite et PostgreSQL
- `static/index.html` : interface utilisateur
- `static/styles.css` : styles responsives
- `static/app.js` : logique front-end et appels API
- `requirements.txt` : dependances Python
- `Dockerfile` : image de deploiement
- `railway.json` : configuration de deploiement Railway

## Deploiement Docker

1. Construire l'image : `docker build -t registre-qualite .`
2. Demarrer le conteneur :
   `docker run -p 8765:8765 -e HOST=0.0.0.0 -e PORT=8765 -e DATABASE_URL=postgresql://user:password@host:5432/dbname -e ADMIN_PASSWORD=MotDePasseFort registre-qualite`
3. Ouvrir `http://localhost:8765`

Pour la production, utilisez PostgreSQL via `DATABASE_URL`.
Pour le developpement local en SQLite, vous pouvez encore monter un volume et passer `-e DB_PATH=/app/data/quality_sheets.db`.

## Publication sur Render

Le projet contient maintenant [render.yaml](./render.yaml), compatible avec les Blueprints Render.

### Etapes

1. Envoyer le projet sur GitHub
2. Ouvrir Render
3. Choisir `New` puis `Blueprint`
4. Connecter le depot GitHub
5. Valider la creation du service web `registre-qualite` et de la base PostgreSQL `registre-qualite-db`
6. Saisir une valeur forte pour `ADMIN_PASSWORD` quand Render la demande
7. Lancer le deploiement

### Resultat

- Render cree automatiquement l'application web
- Render cree automatiquement PostgreSQL
- `DATABASE_URL` est relie automatiquement a la base
- l'application obtient une URL publique en `https://...onrender.com`
- le site fonctionne sur PC et mobile via navigateur

### Domaine

Apres deploiement, vous pouvez :

- garder l'URL Render en `onrender.com`
- ou ajouter votre propre domaine dans les parametres du service

### Variables importantes

- `DATABASE_URL` : fourni automatiquement par Render via la base PostgreSQL
- `ADMIN_PASSWORD` : a fournir manuellement
- `COOKIE_SECURE=true` : deja prevu dans `render.yaml`

## Publication sur Railway

Le projet contient maintenant [railway.json](./railway.json), pour simplifier un essai sur Railway avec le meme `Dockerfile`.

### Quand choisir Railway

- si vous voulez tester une autre plateforme que Render
- si vous voulez reutiliser directement le depot GitHub existant
- si vous voulez garder PostgreSQL en production

### Etapes

1. Ouvrir `https://railway.app`
2. Se connecter avec GitHub
3. Creer un nouveau projet vide
4. Ajouter une base `PostgreSQL`
5. Ajouter un service depuis GitHub et choisir le depot `registre-qualite`
6. Railway detecte `railway.json` et le `Dockerfile`
7. Definir les variables d'environnement du service :
   - `HOST=0.0.0.0`
   - `ADMIN_USERNAME=admin`
   - `ADMIN_NAME=Administrateur Qualite`
   - `ADMIN_PASSWORD=un mot de passe fort`
   - `COOKIE_SECURE=true`
8. Relier `DATABASE_URL` a la variable fournie par le service PostgreSQL Railway
9. Lancer le deploiement

### Ce que fait `railway.json`

- force la construction avec le `Dockerfile`
- configure le health check sur `/api/health`
- applique une politique de redemarrage en cas d'echec

### Notes utiles

- l'application lit deja `PORT`, donc Railway peut injecter son port dynamiquement
- l'application lit deja `DATABASE_URL`, donc PostgreSQL Railway est compatible sans modification du code
- pour un simple test, Railway propose un essai gratuit selon les conditions du compte et de la verification GitHub
- pour un usage durable en production, verifiez ensuite les limites et la facturation Railway

## Mise en ligne

Pour une mise en ligne internet ou intranet :

- heberger le serveur Python sur une machine accessible aux utilisateurs
- placer un reverse proxy HTTPS devant l'application
- configurer `DATABASE_URL` vers une base PostgreSQL managée ou hebergee par votre entreprise
- definir un mot de passe administrateur fort avant le premier demarrage
- sauvegarder regulierement la base PostgreSQL
