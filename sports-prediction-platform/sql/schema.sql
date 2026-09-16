-- =============================================================================
--  Sports Prediction Platform — schéma PostgreSQL 16
-- =============================================================================
--  Conventions
--    * Schémas logiques : raw, core, stats, market, features, ml, bet, ops
--    * Clés primaires : BIGINT GENERATED ALWAYS AS IDENTITY, sauf tables de
--      référence courtes (SMALLINT) et tables temporelles (clé composite)
--    * Tout horodatage est TIMESTAMPTZ en UTC. Aucune exception.
--    * Bitemporalité : valid_from/valid_to (temps métier)
--                      recorded_at/superseded_at (temps de connaissance)
--    * Les montants monétaires sont NUMERIC(14,4). Jamais de float.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS stats;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS bet;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- matching flou des noms d'équipes
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- contraintes d'exclusion temporelles

-- =============================================================================
--  1. RAW — append-only, immuable, jamais de UPDATE ni de DELETE
-- =============================================================================

CREATE TABLE raw.providers (
    provider_id     SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT        NOT NULL UNIQUE,
    name            TEXT        NOT NULL,
    kind            TEXT        NOT NULL
                    CHECK (kind IN ('fixtures','stats','odds','weather','injuries','lineups','ratings')),
    base_url        TEXT,
    trust_score     NUMERIC(3,2) NOT NULL DEFAULT 0.50,   -- arbitrage des conflits
    rate_limit_per_min INT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE raw.ingestion_runs (
    run_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id     SMALLINT    NOT NULL REFERENCES raw.providers,
    endpoint        TEXT        NOT NULL,
    request_params  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    http_status     INT,
    row_count       INT,
    status          TEXT        NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','success','partial','failed')),
    error_message   TEXT,
    payload_sha256  TEXT                                   -- déduplication
);
CREATE INDEX ix_ingestion_runs_provider_time ON raw.ingestion_runs (provider_id, started_at DESC);
CREATE INDEX ix_ingestion_runs_status ON raw.ingestion_runs (status) WHERE status <> 'success';

-- Table partitionnée par mois : la volumétrie vient d'ici (surtout les cotes)
CREATE TABLE raw.observations (
    observation_id  BIGINT GENERATED ALWAYS AS IDENTITY,
    run_id          BIGINT      NOT NULL REFERENCES raw.ingestion_runs,
    provider_id     SMALLINT    NOT NULL REFERENCES raw.providers,
    entity_kind     TEXT        NOT NULL,   -- 'match','team','odds','lineup',...
    provider_entity_id TEXT,                -- identifiant chez le provider
    payload         JSONB       NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,   -- INSTANT DE DISPONIBILITÉ : sacré
    payload_sha256  TEXT        NOT NULL,
    PRIMARY KEY (observation_id, fetched_at)
) PARTITION BY RANGE (fetched_at);

CREATE INDEX ix_observations_entity   ON raw.observations (entity_kind, provider_entity_id, fetched_at DESC);
CREATE INDEX ix_observations_payload  ON raw.observations USING GIN (payload jsonb_path_ops);
CREATE UNIQUE INDEX ux_observations_dedupe
    ON raw.observations (provider_id, entity_kind, provider_entity_id, payload_sha256, fetched_at);

-- Exemple de partition (créées automatiquement par l'orchestrateur)
CREATE TABLE raw.observations_2026_09 PARTITION OF raw.observations
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

REVOKE UPDATE, DELETE ON raw.observations FROM PUBLIC;

-- Table de correspondance provider -> entité canonique
CREATE TABLE raw.entity_mappings (
    provider_id     SMALLINT NOT NULL REFERENCES raw.providers,
    entity_kind     TEXT     NOT NULL,
    provider_entity_id TEXT  NOT NULL,
    canonical_id    BIGINT   NOT NULL,
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    resolved_by     TEXT     NOT NULL DEFAULT 'auto' CHECK (resolved_by IN ('auto','manual','fuzzy')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider_id, entity_kind, provider_entity_id)
);
CREATE INDEX ix_entity_mappings_canonical ON raw.entity_mappings (entity_kind, canonical_id);

-- =============================================================================
--  2. CORE — modèle canonique, agnostique au sport
-- =============================================================================

CREATE TABLE core.sports (
    sport_id        SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,          -- 'football','basketball','tennis'
    name            TEXT NOT NULL,
    competitor_kind TEXT NOT NULL CHECK (competitor_kind IN ('team','individual')),
    allows_draw     BOOLEAN NOT NULL,
    score_model     TEXT NOT NULL                  -- 'bivariate_poisson','normal_diff','markov_point'
                    CHECK (score_model IN ('bivariate_poisson','normal_diff','markov_point','custom')),
    default_period_count SMALLINT
);

CREATE TABLE core.countries (
    country_id      SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iso2            CHAR(2) NOT NULL UNIQUE,
    name            TEXT NOT NULL
);

CREATE TABLE core.competitions (
    competition_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    country_id      SMALLINT REFERENCES core.countries,      -- NULL = international
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    tier            SMALLINT NOT NULL DEFAULT 1,             -- 1 = élite
    format          TEXT NOT NULL CHECK (format IN ('league','cup','group_knockout','tournament')),
    gender          TEXT NOT NULL DEFAULT 'M' CHECK (gender IN ('M','F','X')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (sport_id, code, gender)
);
CREATE INDEX ix_competitions_sport ON core.competitions (sport_id, tier);

CREATE TABLE core.seasons (
    season_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    competition_id  INT NOT NULL REFERENCES core.competitions,
    label           TEXT NOT NULL,                  -- '2025/2026'
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    matchday_count  SMALLINT,
    points_win      SMALLINT NOT NULL DEFAULT 3,
    points_draw     SMALLINT NOT NULL DEFAULT 1,
    UNIQUE (competition_id, label),
    CHECK (end_date > start_date)
);

CREATE TABLE core.venues (
    venue_id        INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    country_id      SMALLINT REFERENCES core.countries,
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6),
    altitude_m      SMALLINT,
    capacity        INT,
    surface         TEXT,                            -- 'grass','synthetic','hard','clay','grass_tennis'
    is_indoor       BOOLEAN NOT NULL DEFAULT FALSE,
    timezone        TEXT NOT NULL DEFAULT 'UTC'
);
CREATE INDEX ix_venues_geo ON core.venues (latitude, longitude);

-- Compétiteur = équipe OU joueur individuel. Une seule table : le noyau
-- ne doit pas distinguer football et tennis.
CREATE TABLE core.competitors (
    competitor_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    kind            TEXT NOT NULL CHECK (kind IN ('team','individual')),
    name            TEXT NOT NULL,
    short_name      TEXT,
    country_id      SMALLINT REFERENCES core.countries,
    home_venue_id   INT REFERENCES core.venues,
    founded_year    SMALLINT,
    -- champs individuels (NULL pour les équipes)
    birth_date      DATE,
    height_cm       SMALLINT,
    plays_hand      TEXT CHECK (plays_hand IN ('R','L')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    external_refs   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_competitors_sport_name ON core.competitors (sport_id, name);
CREATE INDEX ix_competitors_name_trgm  ON core.competitors USING GIN (name gin_trgm_ops);

-- Joueurs (membres d'une équipe). Pour le tennis, players = competitors.
CREATE TABLE core.players (
    player_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    full_name       TEXT NOT NULL,
    birth_date      DATE,
    country_id      SMALLINT REFERENCES core.countries,
    primary_position TEXT,
    preferred_foot  TEXT CHECK (preferred_foot IN ('R','L','B')),
    height_cm       SMALLINT,
    external_refs   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_players_name_trgm ON core.players USING GIN (full_name gin_trgm_ops);

-- Appartenance d'un joueur à une équipe : intervalle temporel
CREATE TABLE core.player_spells (
    spell_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id       BIGINT NOT NULL REFERENCES core.players,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    valid_from      DATE NOT NULL,
    valid_to        DATE,                            -- NULL = en cours
    shirt_number    SMALLINT,
    is_loan         BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX ix_player_spells_team ON core.player_spells (competitor_id, valid_from DESC);
CREATE INDEX ix_player_spells_player ON core.player_spells (player_id, valid_from DESC);

CREATE TABLE core.managers (
    manager_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name       TEXT NOT NULL,
    birth_date      DATE,
    country_id      SMALLINT REFERENCES core.countries
);

CREATE TABLE core.manager_spells (
    spell_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manager_id      BIGINT NOT NULL REFERENCES core.managers,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    valid_from      DATE NOT NULL,
    valid_to        DATE,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_manager_spells_team ON core.manager_spells (competitor_id, valid_from DESC);

CREATE TABLE core.referees (
    referee_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    full_name       TEXT NOT NULL,
    country_id      SMALLINT REFERENCES core.countries
);

-- -----------------------------------------------------------------------------
--  MATCHES : table centrale
-- -----------------------------------------------------------------------------
CREATE TABLE core.matches (
    match_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    season_id       INT      NOT NULL REFERENCES core.seasons,
    competition_id  INT      NOT NULL REFERENCES core.competitions,
    stage           TEXT     NOT NULL DEFAULT 'regular',
    matchday        SMALLINT,
    tie_id          BIGINT,                          -- regroupe aller/retour
    leg             SMALLINT CHECK (leg IN (1,2)),
    kickoff_utc     TIMESTAMPTZ NOT NULL,
    local_timezone  TEXT,
    venue_id        INT REFERENCES core.venues,
    is_neutral_venue BOOLEAN NOT NULL DEFAULT FALSE,
    is_behind_closed_doors BOOLEAN NOT NULL DEFAULT FALSE,
    home_competitor_id BIGINT NOT NULL REFERENCES core.competitors,
    away_competitor_id BIGINT NOT NULL REFERENCES core.competitors,
    referee_id      BIGINT REFERENCES core.referees,
    best_of         SMALLINT,                        -- tennis : 3 ou 5
    status          TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled','live','finished','postponed','cancelled','abandoned','walkover')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (home_competitor_id <> away_competitor_id)
);
CREATE INDEX ix_matches_kickoff        ON core.matches (kickoff_utc);
CREATE INDEX ix_matches_season         ON core.matches (season_id, kickoff_utc);
CREATE INDEX ix_matches_home           ON core.matches (home_competitor_id, kickoff_utc DESC);
CREATE INDEX ix_matches_away           ON core.matches (away_competitor_id, kickoff_utc DESC);
CREATE INDEX ix_matches_upcoming       ON core.matches (kickoff_utc) WHERE status = 'scheduled';
CREATE INDEX ix_matches_tie            ON core.matches (tie_id) WHERE tie_id IS NOT NULL;

CREATE TABLE core.match_results (
    match_id        BIGINT PRIMARY KEY REFERENCES core.matches,
    home_score      SMALLINT NOT NULL,
    away_score      SMALLINT NOT NULL,
    home_score_ht   SMALLINT,
    away_score_ht   SMALLINT,
    period_scores   JSONB,        -- [{p:1,h:1,a:0},...] : quart-temps, sets
    went_extra_time BOOLEAN NOT NULL DEFAULT FALSE,
    went_penalties  BOOLEAN NOT NULL DEFAULT FALSE,
    home_score_pens SMALLINT,
    away_score_pens SMALLINT,
    outcome_1x2     CHAR(1) GENERATED ALWAYS AS (
                        CASE WHEN home_score > away_score THEN 'H'
                             WHEN home_score < away_score THEN 'A'
                             ELSE 'D' END) STORED,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (home_score >= 0 AND away_score >= 0)
);
CREATE INDEX ix_match_results_outcome ON core.match_results (outcome_1x2);

CREATE TABLE core.match_events (
    event_id        BIGINT GENERATED ALWAYS AS IDENTITY,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    period          SMALLINT NOT NULL,
    minute          SMALLINT,
    second          SMALLINT,
    competitor_id   BIGINT REFERENCES core.competitors,
    player_id       BIGINT REFERENCES core.players,
    related_player_id BIGINT REFERENCES core.players,
    event_type      TEXT NOT NULL,     -- 'goal','card','sub','shot','corner','foul','ace',...
    detail          TEXT,
    x               NUMERIC(5,2),      -- coordonnées normalisées 0-100
    y               NUMERIC(5,2),
    xg              NUMERIC(5,4),
    body_part       TEXT,
    is_set_piece    BOOLEAN,
    sequence_id     BIGINT,            -- regroupe les événements d'une possession
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, match_id)
) PARTITION BY HASH (match_id);

CREATE TABLE core.match_events_p0 PARTITION OF core.match_events FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE core.match_events_p1 PARTITION OF core.match_events FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE core.match_events_p2 PARTITION OF core.match_events FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE core.match_events_p3 PARTITION OF core.match_events FOR VALUES WITH (MODULUS 4, REMAINDER 3);

CREATE INDEX ix_match_events_match ON core.match_events (match_id, period, minute);
CREATE INDEX ix_match_events_player ON core.match_events (player_id, event_type);

-- -----------------------------------------------------------------------------
--  Compositions, disponibilités, météo
-- -----------------------------------------------------------------------------
CREATE TABLE core.lineups (
    lineup_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    source          TEXT NOT NULL CHECK (source IN ('predicted','official')),
    formation       TEXT,
    published_at    TIMESTAMPTZ NOT NULL,   -- ← instant de disponibilité
    provider_id     SMALLINT REFERENCES raw.providers,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (match_id, competitor_id, source, published_at)
);
CREATE INDEX ix_lineups_match ON core.lineups (match_id, published_at DESC);

CREATE TABLE core.lineup_players (
    lineup_id       BIGINT NOT NULL REFERENCES core.lineups ON DELETE CASCADE,
    player_id       BIGINT NOT NULL REFERENCES core.players,
    role            TEXT NOT NULL CHECK (role IN ('starter','bench','out')),
    position        TEXT,
    grid_x          SMALLINT,
    grid_y          SMALLINT,
    probability     NUMERIC(4,3),          -- rempli si source='predicted'
    PRIMARY KEY (lineup_id, player_id)
);

CREATE TABLE core.availabilities (
    availability_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id       BIGINT NOT NULL REFERENCES core.players,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    status          TEXT NOT NULL CHECK (status IN ('injured','suspended','doubtful','international_duty','personal','fit')),
    injury_type     TEXT,
    expected_return DATE,
    valid_from      TIMESTAMPTZ NOT NULL,   -- temps métier
    valid_to        TIMESTAMPTZ,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),   -- temps de connaissance
    superseded_at   TIMESTAMPTZ,
    provider_id     SMALLINT REFERENCES raw.providers,
    confidence      NUMERIC(3,2) DEFAULT 1.00
);
CREATE INDEX ix_availabilities_player ON core.availabilities (player_id, valid_from DESC);
CREATE INDEX ix_availabilities_team_active ON core.availabilities (competitor_id, valid_from DESC)
    WHERE superseded_at IS NULL;

CREATE TABLE core.weather_observations (
    weather_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    kind            TEXT NOT NULL CHECK (kind IN ('forecast','actual')),
    horizon_hours   SMALLINT,               -- 72, 24, 3 ... NULL si actual
    fetched_at      TIMESTAMPTZ NOT NULL,   -- instant de disponibilité
    temperature_c   NUMERIC(4,1),
    feels_like_c    NUMERIC(4,1),
    precipitation_mm NUMERIC(5,2),
    wind_speed_kmh  NUMERIC(5,1),
    wind_gust_kmh   NUMERIC(5,1),
    humidity_pct    SMALLINT,
    snow_mm         NUMERIC(5,2),
    condition_code  TEXT,
    UNIQUE (match_id, kind, horizon_hours, fetched_at)
);
CREATE INDEX ix_weather_match ON core.weather_observations (match_id, fetched_at DESC);

-- =============================================================================
--  3. STATS — une table par sport, typée fort + extra JSONB
-- =============================================================================

CREATE TABLE stats.football_team_match (
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    is_home         BOOLEAN NOT NULL,
    goals           SMALLINT,
    goals_conceded  SMALLINT,
    xg              NUMERIC(6,4),
    xg_against      NUMERIC(6,4),
    npxg            NUMERIC(6,4),
    xgot            NUMERIC(6,4),
    shots           SMALLINT,
    shots_on_target SMALLINT,
    shots_in_box    SMALLINT,
    big_chances     SMALLINT,
    big_chances_missed SMALLINT,
    possession_pct  NUMERIC(4,1),
    passes          SMALLINT,
    passes_completed SMALLINT,
    progressive_passes SMALLINT,
    progressive_carries SMALLINT,
    box_touches     SMALLINT,
    ppda            NUMERIC(6,2),
    def_line_height_m NUMERIC(5,2),
    corners         SMALLINT,
    offsides        SMALLINT,
    fouls           SMALLINT,
    fouls_drawn     SMALLINT,
    yellow_cards    SMALLINT,
    red_cards       SMALLINT,
    penalties_awarded SMALLINT,
    penalties_scored  SMALLINT,
    penalties_conceded SMALLINT,
    setpiece_xg     NUMERIC(6,4),
    counter_shots   SMALLINT,
    psxg_faced      NUMERIC(6,4),
    formation       TEXT,
    provider_id     SMALLINT REFERENCES raw.providers,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at   TIMESTAMPTZ,
    extra           JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (match_id, competitor_id, recorded_at),
    CHECK (shots_on_target IS NULL OR shots IS NULL OR shots_on_target <= shots),
    CHECK (passes_completed IS NULL OR passes IS NULL OR passes_completed <= passes),
    CHECK (possession_pct IS NULL OR possession_pct BETWEEN 0 AND 100)
);
CREATE INDEX ix_fb_team_match_team ON stats.football_team_match (competitor_id, match_id)
    WHERE superseded_at IS NULL;

CREATE TABLE stats.basketball_team_match (
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    is_home         BOOLEAN NOT NULL,
    points          SMALLINT,
    points_allowed  SMALLINT,
    fga             SMALLINT,
    fgm             SMALLINT,
    fg3a            SMALLINT,
    fg3m            SMALLINT,
    fta             SMALLINT,
    ftm             SMALLINT,
    orb             SMALLINT,
    drb             SMALLINT,
    assists         SMALLINT,
    turnovers       SMALLINT,
    steals          SMALLINT,
    blocks          SMALLINT,
    fouls           SMALLINT,
    possessions     NUMERIC(6,2),
    pace            NUMERIC(6,2),
    ortg            NUMERIC(6,2),
    drtg            NUMERIC(6,2),
    efg_pct         NUMERIC(5,4),
    ts_pct          NUMERIC(5,4),
    tov_pct         NUMERIC(5,4),
    orb_pct         NUMERIC(5,4),
    ft_rate         NUMERIC(5,4),
    minutes_played  NUMERIC(6,2),
    provider_id     SMALLINT REFERENCES raw.providers,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at   TIMESTAMPTZ,
    extra           JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (match_id, competitor_id, recorded_at),
    CHECK (fgm IS NULL OR fga IS NULL OR fgm <= fga),
    CHECK (fg3m IS NULL OR fg3a IS NULL OR fg3m <= fg3a)
);

CREATE TABLE stats.tennis_competitor_match (
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    sets_won        SMALLINT,
    games_won       SMALLINT,
    aces            SMALLINT,
    double_faults   SMALLINT,
    first_serve_in  SMALLINT,
    first_serve_total SMALLINT,
    first_serve_won SMALLINT,
    second_serve_won SMALLINT,
    second_serve_total SMALLINT,
    service_games   SMALLINT,
    service_games_won SMALLINT,
    break_points_faced SMALLINT,
    break_points_saved SMALLINT,
    break_points_converted SMALLINT,
    return_points_won SMALLINT,
    return_points_total SMALLINT,
    total_points_won SMALLINT,
    minutes_played  SMALLINT,
    retired         BOOLEAN NOT NULL DEFAULT FALSE,
    provider_id     SMALLINT REFERENCES raw.providers,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at   TIMESTAMPTZ,
    extra           JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (match_id, competitor_id, recorded_at),
    CHECK (first_serve_in IS NULL OR first_serve_total IS NULL OR first_serve_in <= first_serve_total)
);

CREATE TABLE stats.player_match (
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    player_id       BIGINT NOT NULL REFERENCES core.players,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    minutes_played  NUMERIC(5,2),
    started         BOOLEAN,
    position        TEXT,
    goals           SMALLINT,
    assists         SMALLINT,
    xg              NUMERIC(6,4),
    xa              NUMERIC(6,4),
    shots           SMALLINT,
    key_passes      SMALLINT,
    touches         SMALLINT,
    duels_won       SMALLINT,
    tackles         SMALLINT,
    interceptions   SMALLINT,
    yellow_cards    SMALLINT,
    red_cards       SMALLINT,
    rating          NUMERIC(4,2),
    -- basketball
    points          SMALLINT,
    rebounds        SMALLINT,
    plus_minus      SMALLINT,
    provider_id     SMALLINT REFERENCES raw.providers,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at   TIMESTAMPTZ,
    extra           JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (match_id, player_id, recorded_at)
);
CREATE INDEX ix_player_match_player ON stats.player_match (player_id, match_id)
    WHERE superseded_at IS NULL;

CREATE TABLE stats.referee_match (
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    referee_id      BIGINT NOT NULL REFERENCES core.referees,
    fouls_called    SMALLINT,
    yellow_cards    SMALLINT,
    red_cards       SMALLINT,
    penalties       SMALLINT,
    added_time_min  NUMERIC(4,1),
    PRIMARY KEY (match_id, referee_id)
);

-- =============================================================================
--  4. MARKET — bookmakers, marchés, cotes
-- =============================================================================

CREATE TABLE market.bookmakers (
    bookmaker_id    SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('bookmaker','exchange','sharp','aggregator')),
    is_sharp        BOOLEAN NOT NULL DEFAULT FALSE,   -- Pinnacle & co : référence
    commission_pct  NUMERIC(4,3),                     -- exchanges
    country_id      SMALLINT REFERENCES core.countries,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE market.market_types (
    market_type_id  SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,   -- '1X2','OU','AH','BTTS','CS','CORNERS_OU',...
    name            TEXT NOT NULL,
    sport_id        SMALLINT REFERENCES core.sports,   -- NULL = multi-sport
    has_line        BOOLEAN NOT NULL DEFAULT FALSE,    -- handicap / total
    outcome_count   SMALLINT,
    is_symmetric    BOOLEAN NOT NULL DEFAULT FALSE,    -- 2 issues complémentaires
    settlement_rule TEXT NOT NULL                      -- identifiant de la fonction de dénouement
);

CREATE TABLE market.selections (
    selection_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    market_type_id  SMALLINT NOT NULL REFERENCES market.market_types,
    line            NUMERIC(5,2),             -- 2.5, -0.75 ... NULL si sans ligne
    side            TEXT NOT NULL,            -- 'H','D','A','OVER','UNDER','YES','NO','1-0',...
    player_id       BIGINT REFERENCES core.players,   -- player props
    period          TEXT NOT NULL DEFAULT 'FT',       -- 'FT','HT','Q1','SET1'
    UNIQUE (match_id, market_type_id, line, side, player_id, period)
);
CREATE INDEX ix_selections_match ON market.selections (match_id, market_type_id);

-- Table des snapshots de cotes : LA table volumineuse (~10^8 lignes/an)
CREATE TABLE market.odds_snapshots (
    snapshot_id     BIGINT GENERATED ALWAYS AS IDENTITY,
    selection_id    BIGINT   NOT NULL,
    bookmaker_id    SMALLINT NOT NULL REFERENCES market.bookmakers,
    odds_decimal    NUMERIC(8,3) NOT NULL CHECK (odds_decimal > 1.0),
    captured_at     TIMESTAMPTZ NOT NULL,
    is_opening      BOOLEAN NOT NULL DEFAULT FALSE,
    is_closing      BOOLEAN NOT NULL DEFAULT FALSE,
    max_stake       NUMERIC(12,2),            -- limite affichée = proxy de liquidité
    volume_matched  NUMERIC(14,2),            -- exchanges
    is_suspended    BOOLEAN NOT NULL DEFAULT FALSE,
    provider_id     SMALLINT REFERENCES raw.providers,
    PRIMARY KEY (snapshot_id, captured_at)
) PARTITION BY RANGE (captured_at);

CREATE TABLE market.odds_snapshots_2026_09 PARTITION OF market.odds_snapshots
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE INDEX ix_odds_selection_time ON market.odds_snapshots (selection_id, captured_at DESC);
CREATE INDEX ix_odds_book_time      ON market.odds_snapshots (bookmaker_id, captured_at DESC);
CREATE INDEX ix_odds_closing        ON market.odds_snapshots (selection_id) WHERE is_closing;
CREATE INDEX ix_odds_opening        ON market.odds_snapshots (selection_id) WHERE is_opening;

-- Vue matérialisée des cotes courantes : évite un DISTINCT ON coûteux à chaque requête
CREATE MATERIALIZED VIEW market.current_odds AS
SELECT DISTINCT ON (o.selection_id, o.bookmaker_id)
       o.selection_id, o.bookmaker_id, o.odds_decimal, o.captured_at, o.max_stake
FROM   market.odds_snapshots o
WHERE  o.is_suspended = FALSE
ORDER  BY o.selection_id, o.bookmaker_id, o.captured_at DESC;
CREATE UNIQUE INDEX ux_current_odds ON market.current_odds (selection_id, bookmaker_id);

-- Probabilités de marché dévigorisées, calculées par livre et par méthode
CREATE TABLE market.market_probabilities (
    match_id        BIGINT   NOT NULL REFERENCES core.matches,
    market_type_id  SMALLINT NOT NULL REFERENCES market.market_types,
    line            NUMERIC(5,2),
    bookmaker_id    SMALLINT REFERENCES market.bookmakers,   -- NULL = consensus
    method          TEXT NOT NULL CHECK (method IN ('proportional','additive','odds_ratio','shin','power')),
    as_of_ts        TIMESTAMPTZ NOT NULL,
    probabilities   JSONB NOT NULL,           -- {"H":0.4617,"D":0.2731,"A":0.2652}
    overround       NUMERIC(6,4) NOT NULL,
    shin_z          NUMERIC(6,4),
    n_bookmakers    SMALLINT,
    dispersion      NUMERIC(6,4),
    PRIMARY KEY (match_id, market_type_id, line, bookmaker_id, method, as_of_ts)
);
CREATE INDEX ix_market_prob_match ON market.market_probabilities (match_id, as_of_ts DESC);

CREATE TABLE market.odds_movements (
    movement_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    selection_id    BIGINT NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL,
    window_minutes  SMALLINT NOT NULL,
    odds_before     NUMERIC(8,3) NOT NULL,
    odds_after      NUMERIC(8,3) NOT NULL,
    delta_logodds   NUMERIC(8,5) NOT NULL,
    z_score         NUMERIC(7,3),              -- normalisé par la volatilité habituelle
    n_books_moved   SMALLINT,
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('drift','steam','reverse_line','limit_change','correction')),
    is_significant  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX ix_movements_selection ON market.odds_movements (selection_id, detected_at DESC);
CREATE INDEX ix_movements_significant ON market.odds_movements (detected_at DESC) WHERE is_significant;

-- =============================================================================
--  5. FEATURES — feature store point-in-time
-- =============================================================================

CREATE TABLE features.definitions (
    feature_id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    version         SMALLINT NOT NULL,
    sport_id        SMALLINT REFERENCES core.sports,    -- NULL = noyau
    entity_kind     TEXT NOT NULL CHECK (entity_kind IN ('match','team_match','player_match','competitor')),
    dtype           TEXT NOT NULL,
    leakage_class   TEXT NOT NULL CHECK (leakage_class IN ('safe','needs_lag','forbidden')),
    null_policy     TEXT NOT NULL,
    params          JSONB NOT NULL DEFAULT '{}'::jsonb,
    formula         TEXT,
    depends_on      TEXT[],
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);

CREATE TABLE features.values (
    match_id        BIGINT      NOT NULL REFERENCES core.matches,
    competitor_id   BIGINT      REFERENCES core.competitors,   -- NULL pour features de match
    as_of_ts        TIMESTAMPTZ NOT NULL,
    feature_set_version TEXT    NOT NULL,
    payload         JSONB       NOT NULL,     -- {"elo_diff@2": 74.3, ...}
    feature_hash    TEXT        NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_missing       SMALLINT    NOT NULL DEFAULT 0,
    completeness    NUMERIC(4,3) NOT NULL,
    PRIMARY KEY (match_id, competitor_id, as_of_ts, feature_set_version)
);
CREATE INDEX ix_features_match ON features.values (match_id, as_of_ts DESC);
CREATE INDEX ix_features_hash  ON features.values (feature_hash);

-- Ratings : snapshot daté, jamais écrasé
CREATE TABLE features.ratings_snapshots (
    rating_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    competition_id  INT REFERENCES core.competitions,
    scheme          TEXT NOT NULL CHECK (scheme IN ('elo','elo_surface','glicko2','poisson_ad','bayes_ad','spi')),
    surface         TEXT,
    valid_from      TIMESTAMPTZ NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL,   -- doit être <= as_of_ts à l'usage
    rating          NUMERIC(9,4) NOT NULL,
    rating_attack   NUMERIC(9,4),
    rating_defense  NUMERIC(9,4),
    rating_sigma    NUMERIC(9,4),
    home_advantage  NUMERIC(9,4),
    n_matches       INT NOT NULL DEFAULT 0,
    model_run_id    BIGINT
);
CREATE INDEX ix_ratings_lookup ON features.ratings_snapshots (competitor_id, scheme, valid_from DESC);
CREATE INDEX ix_ratings_pit    ON features.ratings_snapshots (scheme, computed_at DESC);

CREATE TABLE features.player_impact (
    player_id       BIGINT NOT NULL REFERENCES core.players,
    competitor_id   BIGINT NOT NULL REFERENCES core.competitors,
    computed_at     TIMESTAMPTZ NOT NULL,
    pits_offense    NUMERIC(7,4) NOT NULL,
    pits_defense    NUMERIC(7,4) NOT NULL,
    pits_total      NUMERIC(7,4) NOT NULL,
    sigma           NUMERIC(7,4) NOT NULL,
    minutes_sample  INT NOT NULL,
    prior_weight    NUMERIC(5,3) NOT NULL,
    replacement_player_id BIGINT REFERENCES core.players,
    PRIMARY KEY (player_id, competitor_id, computed_at)
);

-- =============================================================================
--  6. ML — modèles, prédictions, calibration, backtests
-- =============================================================================

CREATE TABLE ml.model_versions (
    model_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,             -- 'football_1x2_ensemble'
    version          TEXT NOT NULL,            -- semver
    sport_id        SMALLINT NOT NULL REFERENCES core.sports,
    market_type_id  SMALLINT REFERENCES market.market_types,
    algorithm       TEXT NOT NULL,             -- 'dixon_coles','lightgbm','stack','elo'
    stage           TEXT NOT NULL DEFAULT 'dev'
                    CHECK (stage IN ('dev','shadow','champion','retired')),
    feature_set_version TEXT NOT NULL,
    hyperparams     JSONB NOT NULL DEFAULT '{}'::jsonb,
    train_start     DATE NOT NULL,
    train_end       DATE NOT NULL,
    trained_at      TIMESTAMPTZ NOT NULL,
    artifact_uri    TEXT NOT NULL,             -- s3://models/...
    artifact_sha256 TEXT NOT NULL,
    git_commit      TEXT,
    metrics         JSONB NOT NULL DEFAULT '{}'::jsonb,
    calibrator_uri  TEXT,
    notes           TEXT,
    UNIQUE (name, version)
);
CREATE INDEX ix_model_versions_stage ON ml.model_versions (sport_id, stage) WHERE stage IN ('champion','shadow');

CREATE TABLE ml.prediction_runs (
    run_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_version_id BIGINT NOT NULL REFERENCES ml.model_versions,
    as_of_ts        TIMESTAMPTZ NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('live','replay','shadow','backtest')),
    trigger         TEXT NOT NULL,             -- 'schedule','lineup_published','odds_move','manual'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    match_count     INT,
    status          TEXT NOT NULL DEFAULT 'running'
);
CREATE INDEX ix_prediction_runs_model ON ml.prediction_runs (model_version_id, as_of_ts DESC);

CREATE TABLE ml.predictions (
    prediction_id   BIGINT GENERATED ALWAYS AS IDENTITY,
    run_id          BIGINT   NOT NULL REFERENCES ml.prediction_runs,
    match_id        BIGINT   NOT NULL REFERENCES core.matches,
    market_type_id  SMALLINT NOT NULL REFERENCES market.market_types,
    line            NUMERIC(5,2),
    as_of_ts        TIMESTAMPTZ NOT NULL,
    probabilities   JSONB    NOT NULL,        -- {"H":0.4824,"D":0.2640,"A":0.2537}
    expected_values JSONB,                    -- {"home_goals":1.62,"away_goals":1.08}
    prob_sigma      JSONB,                    -- incertitude par issue (bootstrap)
    component_probs JSONB,                    -- contributions par sous-modèle
    feature_hash    TEXT     NOT NULL,
    data_quality    NUMERIC(4,3) NOT NULL,
    reliability     NUMERIC(4,3) NOT NULL,
    lineup_status   TEXT NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (prediction_id, as_of_ts)
) PARTITION BY RANGE (as_of_ts);

CREATE TABLE ml.predictions_2026_09 PARTITION OF ml.predictions
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE INDEX ix_predictions_match ON ml.predictions (match_id, market_type_id, as_of_ts DESC);
CREATE INDEX ix_predictions_run   ON ml.predictions (run_id);

CREATE TABLE ml.explanations (
    prediction_id   BIGINT NOT NULL,
    as_of_ts        TIMESTAMPTZ NOT NULL,
    outcome         TEXT NOT NULL,
    base_value      NUMERIC(8,5) NOT NULL,     -- valeur de référence SHAP
    contributions   JSONB NOT NULL,            -- [{"feature":"elo_diff","shap":0.031},...]
    grouped         JSONB NOT NULL,            -- agrégé par famille pour l'UI
    PRIMARY KEY (prediction_id, as_of_ts, outcome)
);

CREATE TABLE ml.calibration_snapshots (
    calibration_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_version_id BIGINT NOT NULL REFERENCES ml.model_versions,
    computed_at     TIMESTAMPTZ NOT NULL,
    window_start    DATE NOT NULL,
    window_end      DATE NOT NULL,
    n_predictions   INT NOT NULL,
    brier_score     NUMERIC(8,6),
    brier_skill     NUMERIC(8,6),
    log_loss        NUMERIC(8,6),
    ece             NUMERIC(8,6),
    mce             NUMERIC(8,6),
    roc_auc         NUMERIC(6,5),
    reliability_bins JSONB NOT NULL,           -- [{bin:0.05,pred:0.048,obs:0.052,n:180},...]
    method          TEXT NOT NULL CHECK (method IN ('isotonic','platt','beta','vector_scaling','none'))
);
CREATE INDEX ix_calibration_model ON ml.calibration_snapshots (model_version_id, computed_at DESC);

CREATE TABLE ml.value_signals (
    signal_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prediction_id   BIGINT NOT NULL,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    selection_id    BIGINT NOT NULL,
    bookmaker_id    SMALLINT NOT NULL REFERENCES market.bookmakers,
    as_of_ts        TIMESTAMPTZ NOT NULL,
    model_prob      NUMERIC(6,5) NOT NULL,
    market_prob     NUMERIC(6,5) NOT NULL,
    fair_odds       NUMERIC(8,3) NOT NULL,
    market_odds     NUMERIC(8,3) NOT NULL,
    edge            NUMERIC(7,5) NOT NULL,
    expected_value  NUMERIC(7,5) NOT NULL,
    kelly_fraction  NUMERIC(7,5) NOT NULL,
    recommended_stake_pct NUMERIC(6,4),
    threshold_passed BOOLEAN NOT NULL,
    suppression_reason TEXT,                   -- pourquoi le signal n'est pas actionnable
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_value_signals_match ON ml.value_signals (match_id, as_of_ts DESC);
CREATE INDEX ix_value_signals_live  ON ml.value_signals (as_of_ts DESC) WHERE threshold_passed;

-- =============================================================================
--  7. BET — backtests et paris (réels ou papier)
-- =============================================================================

CREATE TABLE bet.backtests (
    backtest_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    model_version_id BIGINT NOT NULL REFERENCES ml.model_versions,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    universe        JSONB NOT NULL,            -- compétitions, marchés inclus
    staking_method  TEXT NOT NULL CHECK (staking_method IN ('flat','percent','kelly','fractional_kelly')),
    staking_params  JSONB NOT NULL DEFAULT '{}'::jsonb,
    edge_threshold  NUMERIC(6,5) NOT NULL,
    odds_source     TEXT NOT NULL CHECK (odds_source IN ('best','average','sharp','specific')),
    initial_bankroll NUMERIC(14,2) NOT NULL,
    config_sha256   TEXT NOT NULL,
    git_commit      TEXT,
    ran_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    results         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE bet.bets (
    bet_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    backtest_id     BIGINT REFERENCES bet.backtests,   -- NULL = pari réel/papier live
    signal_id       BIGINT REFERENCES ml.value_signals,
    match_id        BIGINT NOT NULL REFERENCES core.matches,
    selection_id    BIGINT NOT NULL,
    bookmaker_id    SMALLINT NOT NULL REFERENCES market.bookmakers,
    placed_at       TIMESTAMPTZ NOT NULL,
    odds_taken      NUMERIC(8,3) NOT NULL,
    closing_odds    NUMERIC(8,3),
    stake           NUMERIC(14,4) NOT NULL,
    bankroll_before NUMERIC(14,4) NOT NULL,
    model_prob      NUMERIC(6,5) NOT NULL,
    market_prob     NUMERIC(6,5) NOT NULL,
    edge            NUMERIC(7,5) NOT NULL,
    expected_value  NUMERIC(7,5) NOT NULL,
    is_paper        BOOLEAN NOT NULL DEFAULT TRUE,
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','won','lost','void','half_won','half_lost','cashed_out')),
    settled_at      TIMESTAMPTZ,
    payout          NUMERIC(14,4),
    profit          NUMERIC(14,4),
    clv             NUMERIC(7,5),              -- closing line value
    notes           TEXT
);
CREATE INDEX ix_bets_backtest ON bet.bets (backtest_id, placed_at);
CREATE INDEX ix_bets_match    ON bet.bets (match_id);
CREATE INDEX ix_bets_open     ON bet.bets (placed_at DESC) WHERE status = 'open';

CREATE TABLE bet.bankroll_history (
    backtest_id     BIGINT NOT NULL REFERENCES bet.backtests,
    as_of_date      DATE NOT NULL,
    bankroll        NUMERIC(14,4) NOT NULL,
    staked          NUMERIC(14,4) NOT NULL,
    profit          NUMERIC(14,4) NOT NULL,
    n_bets          INT NOT NULL,
    drawdown_pct    NUMERIC(7,4) NOT NULL,
    PRIMARY KEY (backtest_id, as_of_date)
);

-- =============================================================================
--  8. OPS — qualité, fraîcheur, alertes
-- =============================================================================

CREATE TABLE ops.data_quality_checks (
    check_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    check_name      TEXT NOT NULL,
    scope           TEXT NOT NULL,             -- 'match','competition','global'
    scope_id        BIGINT,
    severity        TEXT NOT NULL CHECK (severity IN ('info','warning','error','critical')),
    passed          BOOLEAN NOT NULL,
    observed_value  NUMERIC(14,4),
    expected_range  NUMRANGE,
    details         JSONB,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_dq_failures ON ops.data_quality_checks (checked_at DESC) WHERE NOT passed;

CREATE TABLE ops.data_freshness (
    source_key      TEXT PRIMARY KEY,          -- 'odds:pinnacle','stats:opta:ligue1'
    last_success_at TIMESTAMPTZ NOT NULL,
    expected_interval_minutes INT NOT NULL,
    consecutive_failures INT NOT NULL DEFAULT 0
);

-- is_stale dépend de now() : il ne peut pas être une colonne générée
-- (PostgreSQL exige une expression immutable). C'est une vue.
CREATE VIEW ops.data_freshness_status AS
SELECT f.*,
       f.last_success_at < now() - (f.expected_interval_minutes * INTERVAL '1 minute') AS is_stale,
       EXTRACT(EPOCH FROM (now() - f.last_success_at)) / 60 AS minutes_since_success
FROM   ops.data_freshness f;

CREATE TABLE ops.alerts (
    alert_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    match_id        BIGINT REFERENCES core.matches,
    payload         JSONB NOT NULL,
    dedupe_key      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at    TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ
);
-- date_trunc(text, timestamptz) est STABLE (dépend du fuseau de session) : on
-- force l'UTC pour obtenir une expression IMMUTABLE indexable.
CREATE UNIQUE INDEX ux_alerts_dedupe
    ON ops.alerts (dedupe_key, date_trunc('hour', created_at AT TIME ZONE 'UTC'));
CREATE INDEX ix_alerts_pending ON ops.alerts (created_at DESC) WHERE delivered_at IS NULL;

CREATE TABLE ops.source_conflicts (
    conflict_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_kind     TEXT NOT NULL,
    entity_id       BIGINT NOT NULL,
    field_name      TEXT NOT NULL,
    values_by_provider JSONB NOT NULL,         -- {"opta":2,"sportmonks":3}
    resolved_value  JSONB,
    resolution_rule TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX ix_conflicts_unresolved ON ops.source_conflicts (detected_at DESC) WHERE resolved_at IS NULL;

-- =============================================================================
--  9. Vues utilitaires
-- =============================================================================

-- Dernière prédiction par match et marché
CREATE VIEW ml.latest_predictions AS
SELECT DISTINCT ON (p.match_id, p.market_type_id, p.line)
       p.*
FROM   ml.predictions p
JOIN   ml.prediction_runs r ON r.run_id = p.run_id
JOIN   ml.model_versions m ON m.model_version_id = r.model_version_id
WHERE  r.mode = 'live' AND m.stage = 'champion'
ORDER  BY p.match_id, p.market_type_id, p.line, p.as_of_ts DESC;

-- Matchs à venir avec état de préparation
CREATE VIEW core.upcoming_matches AS
SELECT m.match_id, m.kickoff_utc, m.competition_id,
       ch.name AS home_name, ca.name AS away_name,
       EXISTS (SELECT 1 FROM core.lineups l
               WHERE l.match_id = m.match_id AND l.source = 'official') AS has_official_lineup,
       (SELECT count(DISTINCT o.bookmaker_id)
        FROM market.selections s
        JOIN market.current_odds o ON o.selection_id = s.selection_id
        WHERE s.match_id = m.match_id) AS n_bookmakers
FROM   core.matches m
JOIN   core.competitors ch ON ch.competitor_id = m.home_competitor_id
JOIN   core.competitors ca ON ca.competitor_id = m.away_competitor_id
WHERE  m.status = 'scheduled' AND m.kickoff_utc BETWEEN now() AND now() + INTERVAL '10 days';
