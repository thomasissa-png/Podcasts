# KPI Framework — Les Histoires de Papy Babou

> Produit par @data-analyst — 2026-03-25
> Maturité data : niveau 0 (pas de tracking actif, pré-lancement)
> Statut : pré-lancement — toutes les cibles marquées [HYPOTHÈSE] sont à valider avec données réelles

---

## 1. Validation des personas

### Persona 1 — Sophie (parent catholique pratiquant, 40%)

| Métrique | Source | Seuil de validation |
|----------|--------|---------------------|
| % d'abonnés newsletter ayant ouvert la page "À propos" puis cliqué "Écouter" | Google Analytics 4 (parcours de page) | ≥ 30% des premières écoutes suivent ce parcours |
| Taux d'écoute jusqu'au bout > 80% de la durée | Stats hébergeur podcast (Buzzsprout/RSS) | ≥ 40% des auditeurs dépassent 80% d'un épisode |
| Origine de découverte "recommandation / réseau catholique" | Enquête courte (1 question post-newsletter) | ≥ 35% citent le bouche-à-oreille communautaire |

**Signal d'alerte** : si le taux d'écoute complète est < 30% ou si la durée médiane d'écoute est < 12 min, Sophie n'est pas convaincue par la qualité — revisiter la production audio, pas le contenu.

---

### Persona 2 — Lina (7 ans, 30%)

Lina ne génère pas directement de données analytics — elle écoute via l'appareil de Sophie. Les signaux sont indirects.

| Métrique | Source | Seuil de validation |
|----------|--------|---------------------|
| Taux de ré-écoute du même épisode dans les 7 jours | Stats hébergeur (écoutes multiples même IP/device, même episode_id) | ≥ 10% des écoutes sont des ré-écoutes (comportement enfant qui "veut encore") |
| Abandon < 5 min sur les épisodes à fort contenu émotionnel (Jonas, déluge) | Courbe d'écoute Spotify for Podcasters | Taux d'abandon < 5 min inférieur à 15% sur ces épisodes |
| Écoutes en fin de journée 19h-21h (heure du coucher) | Stats hébergeur (horodatage) | ≥ 25% des écoutes dans cette tranche horaire |

**Signal d'alerte** : si les abandons < 5 min dépassent 20%, le cold open est trop "adulte" pour Lina — Antoine/Noémie doivent parler plus tôt. Si les écoutes du soir sont < 15%, le podcast est consommé différemment du rituel du coucher prévu.

---

### Persona 3 — Noah (10 ans, 30%)

Noah écoute aussi via l'appareil parental mais son comportement laisse des traces mesurables.

| Métrique | Source | Seuil de validation |
|----------|--------|---------------------|
| Taux de rétention à 3 min (premier drop-off) | Courbe d'écoute Spotify for Podcasters | < 20% d'abandons à la marque 3 min |
| Écoutes complètes des épisodes à fort contenu factuel (La Création, David/Goliath) | Stats hébergeur comparé aux autres épisodes | Ces épisodes dans le top 3 des taux d'écoute complète |
| Abonnements suite au premier épisode (next-episode play dans les 48h) | Comportement séquentiel détecté via stats hébergeur | ≥ 20% des auditeurs d'E01 écoutent E02 dans les 48h |

**Signal d'alerte** : si le premier drop-off est à 2 min (avant le cold open complet), Noah décroche trop tôt — le format "trop bébé" est perçu dès l'intro. Si les épisodes "science-forward" ne surperforment pas, Noah n'est pas dans l'audience.

---

### Persona 4 — Camille (parent catho-culturel, levier de croissance)

| Métrique | Source | Seuil de validation |
|----------|--------|---------------------|
| % d'écoutes venant de recherches génériques ("podcast bible enfant", "histoires bibliques enfants") vs termes religieux ("catéchisme enfant", "podcast catholique") | Google Search Console (si podcast indexé) + stats Apple Podcasts | ≥ 40% des découvertes via termes non-confessionnels |
| Taux d'abonnement newsletter sans clic sur les pages "Foi" / "Catéchisme" | Parcours GA4 | ≥ 30% des abonnés n'ont jamais cliqué sur contenus à connotation religieuse explicite |
| Partages sur réseaux non-religieux (si mesurable via UTM) | UTM tracking sur liens de partage | [HYPOTHÈSE — à instrumenter quand les réseaux sociaux seront actifs] |

**Signal d'alerte** : si 100% des abonnés viennent de canaux catholiques explicites, Camille n'est pas touché — le SEO et la communication publique restent trop confessionnels. Corriger le positionnement "culture générale" sur la homepage.

---

## 2. KPIs de base — Funnel AARRR

### North Star Metric
**3 000 écoutes complètes/mois** (seuil de visibilité pour les annonceurs podcast — défini dans project-context.md)

Définition opérationnelle : épisode écouté à ≥ 80% de sa durée.

---

### Funnel AARRR adapté au podcast

| Phase | KPI | Cible 6 mois | Source | Statut |
|-------|-----|-------------|--------|--------|
| **Acquisition** | Visiteurs uniques/mois sur le site | [HYPOTHÈSE : 1 500] | GA4 | À mesurer au lancement |
| **Acquisition** | Abonnés actifs Apple Podcasts + Spotify | [HYPOTHÈSE : 400] | Tableau de bord plateformes | À mesurer |
| **Activation** | % visiteurs site → 1ère écoute | [HYPOTHÈSE : 15-25%] | GA4 + stats hébergeur | À mesurer |
| **Rétention** | % auditeurs E01 → E02 dans les 7 jours | [HYPOTHÈSE : 30%] | Stats hébergeur séquentiel | À mesurer |
| **Rétention** | Taux d'écoute complète (≥ 80%) | [HYPOTHÈSE : 35-45%] | Spotify for Podcasters | À mesurer |
| **Revenu** | Abonnés newsletter | [HYPOTHÈSE : 200] | Formulaire site | À mesurer |
| **Référral** | Écoutes attribuées à un partage | Non mesurable pré-lancement | UTM futur | — |

**Note** : le podcast est pré-lancement, aucune donnée de base disponible. Toutes les cibles ci-dessus sont des [HYPOTHÈSES] à calibrer après les 4 premières semaines de distribution.

---

### KPIs secondaires alignés sur les personas

| KPI | Persona ciblé | Seuil cible | Pourquoi |
|-----|--------------|-------------|---------|
| Taux d'écoute complète ≥ 80% | Sophie | ≥ 40% | Confiance qualité = recommandation bouche-à-oreille |
| Retention épisode 1 → épisode 2 | Noah | ≥ 25% dans 48h | Valide l'accroche cold open |
| Écoutes 19h-21h (rituel soir) | Lina | ≥ 25% du total | Valide le cas d'usage coucher |
| Découverte via recherche non-confessionnelle | Camille | ≥ 35% des sources | Valide le positionnement "culture générale" |

---

### Seuils d'alerte — Action requise si

- Taux d'écoute complète < 25% → problème de durée ou de qualité audio (réviser le montage)
- Drop-off massif entre 0-3 min (> 25%) → cold open insuffisant (réviser l'accroche Acte 1)
- 0 écoute E02 dans les 7 jours après E01 → problème de teasing / abonnement (vérifier le CTA de fin d'épisode)
- 100% des abonnés newsletter = trafic catholique seul → Camille non atteint (réviser SEO et positionnement public)

---

### Outils recommandés (budget 0)

| Besoin | Outil | Coût |
|--------|-------|------|
| Stats écoutes + courbe de rétention | Spotify for Podcasters (gratuit) | 0 |
| Visiteurs site, parcours | Google Analytics 4 (gratuit) | 0 |
| Statistiques Apple Podcasts | Apple Podcasts Connect (gratuit) | 0 |
| Agrégation multi-plateformes | Tableau de bord RSS hébergeur | Inclus hébergeur |

Recommandation : mettre en place GA4 sur le site avant la distribution sur les plateformes. Instrumenter les UTM sur tous les liens de partage dès le lancement.

---

**Handoff → @fullstack**
- Fichiers produits : `docs/analytics/kpi-framework.md`
- Décisions prises : North Star = 3 000 écoutes complètes/mois (≥ 80% de durée). 4 personas avec métriques de validation indirectes (Lina/Noah = comportements observables sur l'appareil parental). Outil recommandé : GA4 + Spotify for Podcasters + Apple Podcasts Connect (budget zéro). A/B testing classique non viable (trafic < 1 000/mois probable au lancement).
- Points d'attention pour le tracking : (1) instrumenter GA4 sur le site public avant distribution, (2) ajouter les UTM sur tous les liens de partage sortants, (3) l'horodatage des écoutes (19h-21h) n'est disponible que via l'hébergeur RSS — vérifier que Buzzsprout expose cette donnée. Le trafic attendu au lancement est inférieur à 1 000 visiteurs/mois — les A/B tests statistiques ne seront pas exploitables avant 6 mois minimum.
