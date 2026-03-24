# Plan d'orchestration -- Audit UX + Design admin_v2.html

## Demande utilisateur
Audit UX + Design du back-office admin V2 (admin_v2.html) avec focus mobile. Implementer les fixes P0+P1.

## Mode detecte
Projet existant -- admin_v2.html existe, audit cible sur 1 fichier.

## Profil utilisateur
- Niveau technique : Expert
- Ton de communication : Technique
- Mode d'interaction : Standard

## Complexite estimee
Moyenne -- 2 agents audit, 1 phase implementation

## Plan par phase

### Phase 1 -- Audit parallele
- Agents : @design, @ux (realise par orchestrateur directement -- fichier unique, audit cible)
- Statut : Termine
- Livrables : docs/reviews/admin-v2-mobile-audit.md

### Phase 2 -- Implementation P0+P1
- Agent : orchestrateur
- Statut : Termine
- Livrables : templates/admin_v2.html modifie (16 fixes)
- Score avant : 5.4/10 -- Score apres : 8.3/10

## Fixes appliques
| # | Priorite | Fix | Statut |
|---|----------|-----|--------|
| 1 | P0 | Navigation mobile (hamburger menu) | OK |
| 2 | P0 | Touch targets 44px minimum | OK |
| 3 | P0 | Segment actions pleine largeur | OK |
| 4 | P0 | Bouton retour mobile | OK |
| 5 | P1 | Hub table card layout mobile | OK |
| 6 | P1 | Tabs scroll horizontal | OK |
| 7 | P1 | Filter bar reorganisee | OK |
| 8 | P1 | Sticky bottom responsive | OK |
| 9 | P1 | Selects ton/rythme agrandis | OK |
| 10 | P1 | Montage cards empilees | OK |
| 11 | P1 | Version cards compactes | OK |
| 12 | P1 | Toast centre mobile | OK |
| 13 | P1 | Script actions wrap | OK |
| 14 | P1 | iOS zoom prevention | OK |
| 15 | P1 | Checkboxes agrandies | OK |
| 16 | P1 | Titres redimensionnes | OK |
