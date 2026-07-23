"""Busca as estatísticas públicas do Trailhead (via GraphQL público, sem login)
e atualiza o bloco entre os marcadores TRAILHEAD_STATS no README.md."""

import json
import re
import urllib.request
from pathlib import Path

GRAPHQL_URL = "https://profile.api.trailhead.com/graphql"
SLUG = "ibressan"
README_PATH = Path(__file__).resolve().parent.parent / "README.md"

RANK_QUERY = """
fragment TrailheadRank on TrailheadRank {
  __typename
  title
  requiredPointsSum
  requiredBadgesCount
  imageUrl
}

fragment PublicProfile on PublicProfile {
  __typename
  trailheadStats {
    __typename
    earnedPointsSum
    earnedBadgesCount
    completedTrailCount
    superbadgeCount
    rank {
      ...TrailheadRank
    }
    learnerStatusLevels {
      __typename
      statusName
      title
      level
      edition
    }
  }
}

query GetTrailheadRank($slug: String, $hasSlug: Boolean!) {
  profile(slug: $slug) @include(if: $hasSlug) {
    ... on PublicProfile {
      ...PublicProfile
    }
    ... on PrivateProfile {
      __typename
    }
  }
}
"""

SKILLS_QUERY = """
fragment EarnedSkill on EarnedSkill {
  __typename
  earnedPointsSum
  id
  skill {
    __typename
    apiName
    id
    name
  }
}

query GetEarnedSkills($slug: String, $hasSlug: Boolean!) {
  profile(slug: $slug) @include(if: $hasSlug) {
    __typename
    ... on PublicProfile {
      id
      earnedSkills {
        ...EarnedSkill
      }
    }
  }
}
"""

TOP_SKILLS_COUNT = 5

CERTIFICATIONS_QUERY = """
query GetUserCertifications($slug: String, $hasSlug: Boolean!) {
  profile(slug: $slug) @include(if: $hasSlug) {
    __typename
    id
    ... on PublicProfile {
      credential {
        certifications {
          title
          logoUrl
          status {
            __typename
            title
            expired
          }
        }
      }
    }
  }
}
"""

SUPERBADGES_QUERY = """
fragment EarnedAward on EarnedAwardBase {
  __typename
  id
  award {
    __typename
    id
    title
    type
    icon
    content {
      __typename
      webUrl
    }
  }
}

query GetTrailheadBadges($slug: String, $hasSlug: Boolean!, $count: Int = 20, $filter: AwardTypeFilter = null) {
  profile(slug: $slug) @include(if: $hasSlug) {
    __typename
    ... on PublicProfile {
      earnedAwards(first: $count, awardType: $filter) {
        edges {
          node {
            ... on EarnedAwardBase {
              ...EarnedAward
            }
          }
        }
      }
    }
  }
}
"""


def graphql(query: str, operation_name: str, variables: dict) -> dict:
    payload = json.dumps(
        {"query": query, "operationName": operation_name, "variables": variables}
    ).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def build_rank_icon(rank: dict) -> str:
    return f'<img src="{rank["imageUrl"]}" width="100" alt="{rank["title"]}" />'


STAR_WORDS = {
    "pentastar": 5,
    "quad": 4,
    "triple": 3,
    "double": 2,
}


def get_star_count(rank_title: str) -> int:
    title = rank_title.lower()
    for word, count in STAR_WORDS.items():
        if word in title:
            return count
    return 1


def clean_rank_title(rank_title: str) -> str:
    return " ".join(w for w in rank_title.split() if w.lower() != "star")


def build_rank_status(rank: dict) -> str:
    stars = "⭐" * get_star_count(rank["title"])
    label = f"{clean_rank_title(rank['title']).upper()} {stars}".strip()
    return f'<span style="color:#4FC3F7;">({label})</span>'


def get_agentblazer_title(learner_status_levels: list) -> str | None:
    levels = [l for l in learner_status_levels if l.get("statusName") == "Agentblazer"]
    if not levels:
        return None
    latest = max(levels, key=lambda l: l.get("edition") or "")
    return latest["title"]


def build_stats_line(stats: dict) -> str:
    points = stats["earnedPointsSum"]
    badges = stats["earnedBadgesCount"]
    trails = stats["completedTrailCount"]
    agentblazer = get_agentblazer_title(stats.get("learnerStatusLevels") or [])

    parts = [
        f"🏅 {points:,} pontos",
        f"🎖️ {badges} badges",
        f"🥾 {trails} trilhas",
    ]
    if agentblazer:
        parts.append(f"🤖 Agentblazer: {agentblazer}")
    parts.append("[Trailhead](https://www.salesforce.com/trailblazer/ibressan)")

    return " &nbsp;·&nbsp; ".join(parts)


def build_skills_line(earned_skills: list) -> str:
    top = sorted(earned_skills, key=lambda s: s["earnedPointsSum"], reverse=True)[:TOP_SKILLS_COUNT]
    items = [f'{s["skill"]["name"]} ({s["earnedPointsSum"]:,})' for s in top]
    return "🧠 **Top Skills:** " + " &nbsp;·&nbsp; ".join(items)


CERTIFICATION_PREFIX = "salesforce certified "


def clean_certification_title(title: str) -> str:
    if title.lower().startswith(CERTIFICATION_PREFIX):
        return title[len(CERTIFICATION_PREFIX):]
    return title


def build_certifications_block(certifications: list) -> str:
    if not certifications:
        return "_Nenhuma certificação encontrada._"

    active = [c for c in certifications if not c["status"]["expired"]]
    cells = [
        f'<td align="center"><img src="{c["logoUrl"]}" alt="{c["title"]}" width="77px" />'
        f'<br/><sub><b>{clean_certification_title(c["title"])}</b></sub></td>'
        for c in active
    ]
    return "<table><tr>\n" + "\n".join(cells) + "\n</tr></table>"


MAX_SUPERBADGES = 6


def build_superbadges_block(edges: list) -> str:
    if not edges:
        return "_Nenhum superbadge encontrado._"

    cells = []
    for edge in edges[:MAX_SUPERBADGES]:
        award = edge["node"]["award"]
        url = award["content"]["webUrl"] if award.get("content") else None
        img = f'<img src="{award["icon"]}" alt="{award["title"]}" width="70px" />'
        badge = f'<a href="{url}">{img}</a>' if url else img
        cells.append(f'<td align="center">{badge}<br/><sub><b>{award["title"]}</b></sub></td>')

    return "<table><tr>\n" + "\n".join(cells) + "\n</tr></table>"


def replace_between(content: str, marker: str, replacement: str, inline: bool) -> str:
    start, end = f"<!-- {marker}_START -->", f"<!-- {marker}_END -->"
    pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        raise RuntimeError(f"Marcadores {marker}_START/END não encontrados no README.md")
    body = replacement if inline else f"\n{replacement}\n"
    return pattern.sub(lambda m: f"{start}{body}{end}", content)


def update_readme(
    rank_icon: str,
    rank_status: str,
    stats_line: str,
    skills_line: str,
    certifications_block: str,
    superbadges_block: str,
) -> None:
    content = README_PATH.read_text(encoding="utf-8")
    content = replace_between(content, "TRAILHEAD_RANK_ICON", rank_icon, inline=True)
    content = replace_between(content, "TRAILHEAD_RANK_STATUS", rank_status, inline=True)
    content = replace_between(content, "TRAILHEAD_STATS", stats_line, inline=False)
    content = replace_between(content, "TRAILHEAD_SKILLS", skills_line, inline=False)
    content = replace_between(
        content, "TRAILHEAD_CERTIFICATIONS", certifications_block, inline=False
    )
    content = replace_between(content, "TRAILHEAD_SUPERBADGES", superbadges_block, inline=False)
    README_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    rank_result = graphql(RANK_QUERY, "GetTrailheadRank", {"slug": SLUG, "hasSlug": True})
    stats = rank_result["data"]["profile"]["trailheadStats"]

    skills_result = graphql(SKILLS_QUERY, "GetEarnedSkills", {"slug": SLUG, "hasSlug": True})
    earned_skills = skills_result["data"]["profile"]["earnedSkills"]

    certs_result = graphql(
        CERTIFICATIONS_QUERY, "GetUserCertifications", {"slug": SLUG, "hasSlug": True}
    )
    certifications = certs_result["data"]["profile"]["credential"]["certifications"]

    superbadges_result = graphql(
        SUPERBADGES_QUERY,
        "GetTrailheadBadges",
        {"slug": SLUG, "hasSlug": True, "count": 20, "filter": "SUPERBADGE"},
    )
    superbadge_edges = superbadges_result["data"]["profile"]["earnedAwards"]["edges"]

    update_readme(
        build_rank_icon(stats["rank"]),
        build_rank_status(stats["rank"]),
        build_stats_line(stats),
        build_skills_line(earned_skills),
        build_certifications_block(certifications),
        build_superbadges_block(superbadge_edges),
    )
    print("README.md atualizado com as estatísticas do Trailhead.")


if __name__ == "__main__":
    main()
