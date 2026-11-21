"""Type de carrosserie déduit de la marque et du modèle saisis (champ « make »), pour l'illustration.

Aucune question de plus à l'utilisateur : on reconnaît les modèles courants en Mauritanie,
quelle que soit l'écriture (« Hilux », « HILUX », « toyota hi-lux »…). Inconnu ou vide → « generic ».
Purement visuel : le type n'entre jamais dans le tarif.
"""
import re
import unicodedata

SEDAN, CITY, SUV, PICKUP, VAN, MINIBUS, GENERIC = "sedan", "city", "suv", "pickup", "van", "minibus", "generic"
BODY_TYPES = (SEDAN, CITY, SUV, PICKUP, VAN, MINIBUS, GENERIC)

# Mots qui disent eux-mêmes la carrosserie : prioritaires sur le modèle
# (« Land Cruiser pick-up » est un pick-up, pas un 4x4 fermé).
BODY_WORDS = {
    PICKUP: ["pick up", "pickup", "double cabine", "simple cabine", "plateau", "benne"],
    MINIBUS: ["minibus", "mini bus", "bus", "autocar"],
    VAN: ["fourgon", "fourgonnette", "camionnette", "camion", "utilitaire", "van"],
    SUV: ["4x4", "suv", "tout terrain"],
    SEDAN: ["berline"],
    CITY: ["citadine"],
}

MODELS = {
    PICKUP: [
        "hilux", "hi lux", "navara", "l200", "l 200", "triton", "d max", "dmax", "ranger", "amarok", "bt 50", "bt50",
        "hardbody", "frontier", "gonow", "wingle", "tunland", "great wall", "land cruiser 79", "lc79", "dyna pick",
    ],
    SUV: [
        "hilux surf", "land cruiser", "landcruiser", "prado", "fj cruiser", "4runner", "4 runner", "rav4", "rav 4", "fortuner", "rush",
        "patrol", "pajero", "montero", "shogun", "discovery", "range rover", "defender", "land rover", "santa fe",
        "santafe", "tucson", "sportage", "sorento", "x trail", "xtrail", "qashqai", "duster", "grand vitara", "vitara",
        "jimny", "terrano", "highlander", "kluger", "sequoia", "lexus lx", "lx 570", "gx 460", "touareg", "tiguan",
        "cherokee", "wrangler", "x5", "x3", "q7", "q5", "classe g", "g class", "ml 350", "gle", "creta", "koleos",
        "h6", "haval", "tank 300", "jetour", "chery tiggo", "tiggo", "cx 5", "cx5", "outlander", "ix35",
    ],
    MINIBUS: ["hiace", "hi ace", "coaster", "rosa", "urvan", "h1", "h 1", "starex", "sprinter", "civilian", "county"],
    VAN: [
        "partner", "berlingo", "kangoo", "caddy", "transit", "ducato", "jumper", "boxer", "master", "trafic", "vito",
        "l300", "l 300", "canter", "dyna", "hino", "hd 65", "hd65", "daily", "expert", "jumpy", "doblo", "townace",
        "town ace", "probox", "succeed",
    ],
    SEDAN: [
        "corolla", "camry", "avensis", "carina", "crown", "mark x", "sunny", "sentra", "almera", "bluebird", "elantra",
        "sonata", "accent", "cerato", "optima", "k5", "civic", "accord", "logan", "passat", "jetta", "classe c",
        "classe e", "c class", "e class", "c 200", "c 220", "c 180", "e 200", "e 220", "e 240", "190", "406", "407",
        "508", "301", "405", "505", "mazda 6", "323", "lancer", "galant", "megane", "symbol", "corsa sedan", "tiida",
    ],
    CITY: [
        "yaris", "vitz", "aygo", "i10", "i 10", "i20", "i 20", "picanto", "rio", "clio", "206", "207", "208", "polo",
        "golf", "sandero", "micra", "swift", "alto", "celerio", "fiesta", "getz", "107", "108", "c3", "panda", "fit",
        "jazz", "march", "spark", "matiz", "twingo", "atos", "kwid", "passo", "starlet",
    ],
}


def _normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Hi-Lux » → « hi lux », « LAND-CRUISER » → « land cruiser »."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _lookup(table: dict[str, list[str]]) -> list[tuple[str, str]]:
    # Les clés les plus longues d'abord : « land cruiser 79 » (pick-up) avant « land cruiser » (4x4).
    pairs = [(_normalize(key), body) for body, keys in table.items() for key in keys]
    return sorted(pairs, key=lambda pair: (-len(pair[0].split()), -len(pair[0])))


_BODY_WORDS = _lookup(BODY_WORDS)
_MODELS = _lookup(MODELS)


def body_type(make: str | None) -> str:
    """Type de carrosserie d'après « marque et modèle » ; « generic » si rien n'est reconnu."""
    text = f" {_normalize(make or '')} "
    if not text.strip():
        return GENERIC
    for table in (_BODY_WORDS, _MODELS):
        for key, body in table:
            if f" {key} " in text:
                return body
    return GENERIC
