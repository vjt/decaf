"""ISO 3166-1 alpha-2 to AdE Quadro RW country code mapping.

The Modello Redditi PF uses Italian-specific numeric codes (3 digits)
for foreign countries, NOT the ISO alpha-2 or alpha-3 codes.

Source: Tabella elenco paesi e territori esteri, Istruzioni Modello
Redditi PF — Agenzia delle Entrate. Subset covers the countries
encountered in real broker data (Schwab/IBKR custodians and common
ETF domiciles). Add codes here as needed.

Use `iso_to_ade_country_code("US")` -> "069".
Returns empty string for unknown codes — caller decides whether
to leave the form field empty or warn the user.
"""

from __future__ import annotations

# Common subset — extend as needed.
ISO_TO_ADE: dict[str, str] = {
    "AT": "008",  # Austria
    "AU": "007",  # Australia
    "BE": "009",  # Belgio
    "BR": "011",  # Brasile
    "CA": "013",  # Canada
    "CH": "071",  # Svizzera
    "CN": "016",  # Cina
    "CY": "101",  # Cipro
    "CZ": "275",  # Repubblica Ceca
    "DE": "094",  # Germania
    "DK": "021",  # Danimarca
    "EE": "257",  # Estonia
    "ES": "067",  # Spagna
    "FI": "028",  # Finlandia
    "FR": "029",  # Francia
    "GB": "031",  # Regno Unito
    "GR": "032",  # Grecia
    "HK": "103",  # Hong Kong
    "HR": "261",  # Croazia
    "HU": "077",  # Ungheria
    "IE": "040",  # Irlanda
    "IL": "182",  # Israele
    "IN": "114",  # India
    "IS": "041",  # Islanda
    "IT": "086",  # Italia (per completezza — non si usa in RW)
    "JP": "088",  # Giappone
    "KR": "084",  # Corea del Sud
    "LI": "090",  # Liechtenstein
    "LT": "259",  # Lituania
    "LU": "092",  # Lussemburgo
    "LV": "258",  # Lettonia
    "MC": "091",  # Monaco
    "MT": "105",  # Malta
    "MX": "046",  # Messico
    "NL": "050",  # Paesi Bassi
    "NO": "048",  # Norvegia
    "NZ": "049",  # Nuova Zelanda
    "PL": "054",  # Polonia
    "PT": "055",  # Portogallo
    "RO": "061",  # Romania
    "SE": "068",  # Svezia
    "SG": "147",  # Singapore
    "SI": "260",  # Slovenia
    "SK": "276",  # Slovacchia
    "TR": "076",  # Turchia
    "TW": "022",  # Taiwan
    "UK": "031",  # alias for GB
    "US": "069",  # Stati Uniti
    "ZA": "078",  # Sudafrica
}


def iso_to_ade_country_code(iso: str) -> str:
    """Return the 3-digit AdE country code for an ISO alpha-2 code.

    Returns empty string if unknown — callers should warn.
    """
    return ISO_TO_ADE.get(iso.upper(), "")
