import requests
import streamlit as st

# =============================
# CONFIG
# =============================
API_BASE = "https://movie-rec-466x.onrender.com" or "http://127.0.0.1:8000"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"

st.set_page_config(page_title="Movie Recommender", page_icon="🎬", layout="wide")

# =============================
# STYLES (minimal modern)
# =============================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>

/* Entire App */
html, body, [class*="css"] {
    font-family: 'Poppins', sans-serif;
}

/* Main Container */
.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
    max-width: 1450px;
}

/* Subtitle */
.small-muted {
    color: #6b7280;
    font-size: 1rem;
    font-weight: 500;
}

/* Movie Title */
.movie-title {
    font-size: 1.08rem;
    font-weight: 600;
    line-height: 1.45rem;
    height: 3rem;
    overflow: hidden;
    text-align: center;
    margin-top: 8px;
}

/* Card */
.card {
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 16px;
    padding: 14px;
    background: rgba(255,255,255,0.7);
}

/* Search Box */
div[data-testid="stTextInput"] input {
    font-family: 'Poppins', sans-serif;
    font-size: 18px !important;
    height: 42px !important;
    line-height: 62px !important;
    padding: 0 16px !important;
    border-radius: 12px !important;
    box-sizing: border-box;
}

/* Search Label */
div[data-testid="stTextInput"] label {
    font-size: 20px !important;
    font-weight: 600 !important;
}

/* Buttons */
.stButton > button {
    font-family: 'Poppins', sans-serif;
    font-size: 16px;
    font-weight: 600;
}

/* Selectbox */
.stSelectbox label {
    font-size: 18px !important;
    font-weight: 600 !important;
}

</style>
""", 
unsafe_allow_html=True
)


# =============================
# STATE + ROUTING (single-file pages)
# =============================
if "view" not in st.session_state:
    st.session_state.view = "home"  # home | details
if "selected_tmdb_id" not in st.session_state:
    st.session_state.selected_tmdb_id = None

qp_view = st.query_params.get("view")
qp_id = st.query_params.get("id")
if qp_view in ("home", "details"):
    st.session_state.view = qp_view
if qp_id:
    try:
        st.session_state.selected_tmdb_id = int(qp_id)
        st.session_state.view = "details"
    except:
        pass


def goto_home():
    st.session_state.view = "home"
    st.query_params["view"] = "home"
    if "id" in st.query_params:
        del st.query_params["id"]
    st.rerun()


def goto_details(tmdb_id: int):
    st.session_state.view = "details"
    st.session_state.selected_tmdb_id = int(tmdb_id)
    st.query_params["view"] = "details"
    st.query_params["id"] = str(int(tmdb_id))
    st.rerun()


# =============================
# API HELPERS
# =============================
@st.cache_data(ttl=30)  # short cache for autocomplete
def api_get_json(path: str, params: dict | None = None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=25)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}: {r.text[:300]}"
        return r.json(), None
    except Exception as e:
        return None, f"Request failed: {e}"


def poster_grid(cards, cols=6, key_prefix="grid"):
    if not cards:
        st.info("No movies to show.")
        return

    rows = (len(cards) + cols - 1) // cols
    idx = 0
    for r in range(rows):
        colset = st.columns(cols)
        for c in range(cols):
            if idx >= len(cards):
                break
            m = cards[idx]
            idx += 1

            tmdb_id = m.get("tmdb_id")
            title = m.get("title", "Untitled")
            poster = m.get("poster_url")

            with colset[c]:
                if poster:
                    st.image(poster, use_column_width=True)
                else:
                    st.write("🖼️ No poster")

                if st.button("Open", key=f"{key_prefix}_{r}_{c}_{idx}_{tmdb_id}"):
                    if tmdb_id:
                        goto_details(tmdb_id)

                st.markdown(
                    f"<div class='movie-title'>{title}</div>", unsafe_allow_html=True
                )


def to_cards_from_tfidf_items(tfidf_items):
    cards = []
    for x in tfidf_items or []:
        tmdb = x.get("tmdb") or {}
        if tmdb.get("tmdb_id"):
            cards.append(
                {
                    "tmdb_id": tmdb["tmdb_id"],
                    "title": tmdb.get("title") or x.get("title") or "Untitled",
                    "poster_url": tmdb.get("poster_url"),
                }
            )
    return cards


# =============================
# IMPORTANT: Robust TMDB search parsing
# Supports BOTH API shapes:
# 1) raw TMDB: {"results":[{id,title,poster_path,...}]}
# 2) list cards: [{tmdb_id,title,poster_url,...}]
# =============================
def parse_tmdb_search_to_cards(data, keyword: str, limit: int = 24):
    """
    Returns:
      suggestions: list[(label, tmdb_id)]
      cards: list[{tmdb_id,title,poster_url}]
    """
    keyword_l = keyword.strip().lower()

    # A) If API returns dict with 'results'
    if isinstance(data, dict) and "results" in data:
        raw = data.get("results") or []
        raw_items = []
        for m in raw:
            title = (m.get("title") or "").strip()
            tmdb_id = m.get("id")
            poster_path = m.get("poster_path")
            if not title or not tmdb_id:
                continue
            raw_items.append(
                {
                    "tmdb_id": int(tmdb_id),
                    "title": title,
                    "poster_url": f"{TMDB_IMG}{poster_path}" if poster_path else None,
                    "release_date": m.get("release_date", ""),
                }
            )

    # B) If API returns already as list
    elif isinstance(data, list):
        raw_items = []
        for m in data:
            # might be {tmdb_id,title,poster_url}
            tmdb_id = m.get("tmdb_id") or m.get("id")
            title = (m.get("title") or "").strip()
            poster_url = m.get("poster_url")
            if not title or not tmdb_id:
                continue
            raw_items.append(
                {
                    "tmdb_id": int(tmdb_id),
                    "title": title,
                    "poster_url": poster_url,
                    "release_date": m.get("release_date", ""),
                }
            )
    else:
        return [], []

    # Word-match filtering (contains)
    matched = [x for x in raw_items if keyword_l in x["title"].lower()]

    # If nothing matched, fallback to raw list (so never blank)
    final_list = matched if matched else raw_items

    # Suggestions = top 10 labels
    suggestions = []
    for x in final_list[:10]:
        year = (x.get("release_date") or "")[:4]
        label = f"{x['title']} ({year})" if year else x["title"]
        suggestions.append((label, x["tmdb_id"]))

    # Cards = top N
    cards = [
        {"tmdb_id": x["tmdb_id"], "title": x["title"], "poster_url": x["poster_url"]}
        for x in final_list[:limit]
    ]
    return suggestions, cards


# =============================
# SIDEBAR (clean)
# =============================
with st.sidebar:

    st.markdown("## 🎬 Menu")

    if st.button("🏠 Home", use_container_width=True):
        goto_home()

    st.markdown("---")
    st.markdown("### 📂 Categories")

    # CSS for equal-sized buttons
    st.markdown("""
    <style>
    div.stButton > button {
        width: 100%;
        height: 45px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

    if "home_category" not in st.session_state:
        st.session_state.home_category = "trending"

    if st.button("🔥 Trending", use_container_width=True):
        st.session_state.home_category = "trending"
        goto_home()

    if st.button("⭐ Popular", use_container_width=True):
        st.session_state.home_category = "popular"
        goto_home()

    if st.button("🏆 Top Rated", use_container_width=True):
        st.session_state.home_category = "top_rated"
        goto_home()

    if st.button("🎥 Now Playing", use_container_width=True):
        st.session_state.home_category = "now_playing"
        goto_home()

    if st.button("📅 Upcoming", use_container_width=True):
        st.session_state.home_category = "upcoming"
        goto_home()

    # Fixed grid
    grid_cols = 6

home_category = st.session_state.home_category


# =============================
# HEADER
# =============================
st.title("NTV Movie Recommender")
st.markdown(
    "<div class='small-muted'>Type keyword → dropdown suggestions + matching results → open → details + recommendations</div>",
    unsafe_allow_html=True,
)
st.divider()

# ==========================================================
# VIEW: HOME
# ==========================================================
if st.session_state.view == "home":

    # -----------------------------
    # Search Box
    # -----------------------------
    st.markdown(
    "<h2 style='font-family:Poppins; font-weight:600; margin-bottom:8px;'>🔍 Search Movies</h2>",
    unsafe_allow_html=True,
)
    typed = st.text_input(
        "🔍 Search Movies",
        placeholder="Type movie name (e.g. Avengers, Batman, Interstellar...)",
        label_visibility="collapsed",
    )

    st.divider()

    # =====================================================
    # SEARCH MODE
    # =====================================================
    if typed.strip():

        if len(typed.strip()) < 2:
            st.warning("Please enter at least 2 characters.")

        else:
            data, err = api_get_json(
                "/tmdb/search",
                params={"query": typed.strip()},
            )

            if err or data is None:
                st.error(f"Search failed: {err}")

            else:
                suggestions, cards = parse_tmdb_search_to_cards(
                    data,
                    typed.strip(),
                    limit=24,
                )

                # Movie Suggestions
                if suggestions:

                    labels = ["Select Movie"] + [s[0] for s in suggestions]

                    selected = st.selectbox(
                        "Suggestions",
                        labels,
                        index=0,
                    )

                    if selected != "Select Movie":
                        movie_map = {s[0]: s[1] for s in suggestions}
                        goto_details(movie_map[selected])

                else:
                    st.info("No matching movies found.")

                st.markdown("## 🎬 Search Results")

                poster_grid(
                    cards,
                    cols=6,
                    key_prefix="search_results",
                )

        st.stop()

    # =====================================================
    # HOME CATEGORY
    # =====================================================

    if "home_category" not in st.session_state:
        st.session_state.home_category = "trending"

    home_category = st.session_state.home_category

    category_title = {
        "trending": "🔥 Trending Movies",
        "popular": "⭐ Popular Movies",
        "top_rated": "🏆 Top Rated Movies",
        "now_playing": "🎥 Now Playing",
        "upcoming": "📅 Upcoming Movies",
    }

    st.markdown(f"## {category_title[home_category]}")

    home_cards, err = api_get_json(
        "/home",
        params={
            "category": home_category,
            "limit": 24,
        },
    )

    if err:
        st.error(err)
        st.stop()

    if not home_cards:
        st.warning("No movies available.")
        st.stop()

    poster_grid(
        home_cards,
        cols=6,
        key_prefix=f"home_{home_category}",
    )

# ==========================================================
# VIEW: DETAILS
# ==========================================================
elif st.session_state.view == "details":
    tmdb_id = st.session_state.selected_tmdb_id
    if not tmdb_id:
        st.warning("No movie selected.")
        if st.button("← Back to Home"):
            goto_home()
        st.stop()

    # Top bar
    a, b = st.columns([3, 1])
    with a:
        st.markdown("### 📄 Movie Details")
    with b:
        if st.button("← Back to Home"):
            goto_home()

    # Details (your FastAPI safe route)
    data, err = api_get_json(f"/movie/id/{tmdb_id}")
    if err or not data:
        st.error(f"Could not load details: {err or 'Unknown error'}")
        st.stop()

    # Layout: Poster LEFT, Details RIGHT
    left, right = st.columns([1, 2.4], gap="large")

    with left:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if data.get("poster_url"):
            st.image(data["poster_url"], use_column_width=True)
        else:
            st.write("🖼️ No poster")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"## {data.get('title','')}")
        release = data.get("release_date") or "-"
        genres = ", ".join([g["name"] for g in data.get("genres", [])]) or "-"
        st.markdown(
            f"<div class='small-muted'>Release: {release}</div>", unsafe_allow_html=True
        )
        st.markdown(
            f"<div class='small-muted'>Genres: {genres}</div>", unsafe_allow_html=True
        )
        st.markdown("---")
        st.markdown("### Overview")
        st.write(data.get("overview") or "No overview available.")
        st.markdown("</div>", unsafe_allow_html=True)

    if data.get("backdrop_url"):
        st.markdown("#### Backdrop")
        st.image(data["backdrop_url"], use_column_width=True)

    st.divider()
    st.markdown("### ✅ Recommendations")

    # Recommendations (TF-IDF + Genre) via your bundle endpoint
    title = (data.get("title") or "").strip()
    if title:
        bundle, err2 = api_get_json(
            "/movie/search",
            params={"query": title, "tfidf_top_n": 12, "genre_limit": 12},
        )

        if not err2 and bundle:
            st.markdown("#### 🔎 Similar Movies (TF-IDF)")
            poster_grid(
                to_cards_from_tfidf_items(bundle.get("tfidf_recommendations")),
                cols=grid_cols,
                key_prefix="details_tfidf",
            )

            st.markdown("#### 🎭 More Like This (Genre)")
            poster_grid(
                bundle.get("genre_recommendations", []),
                cols=grid_cols,
                key_prefix="details_genre",
            )
        else:
            st.info("Showing Genre recommendations (fallback).")
            genre_only, err3 = api_get_json(
                "/recommend/genre", params={"tmdb_id": tmdb_id, "limit": 18}
            )
            if not err3 and genre_only:
                poster_grid(
                    genre_only, cols=grid_cols, key_prefix="details_genre_fallback"
                )
            else:
                st.warning("No recommendations available right now.")
    else:
        st.warning("No title available to compute recommendations.")