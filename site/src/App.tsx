import {
  InstantSearch,
  SearchBox,
  Hits,
  Pagination,
  Stats,
  SortBy,
  Configure,
} from "react-instantsearch";
import { history } from "instantsearch.js/es/lib/routers";
import { searchClient, INDEX_NAME, hasCredentials } from "./lib/algolia";
import { Hit } from "./components/Hit";
import { Player } from "./components/Player";
import { CountedRefinementList } from "./components/CountedRefinementList";
import { YearTimeline } from "./components/YearTimeline";
import { SchoolMap } from "./components/SchoolMap";
import { ArtistModal } from "./components/ArtistModal";
import { FocusStrip } from "./components/FocusStrip";
import { FavoritesToggle } from "./components/FavoritesToggle";
import { useFocusStore, composeFocusFilters } from "./hooks/useFocusStore";
import {
  useFavoritesStore,
  composeFavoritesFilters,
} from "./hooks/useFavoritesStore";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import "./App.css";

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function App() {
  const focusNow = useFocusStore((s) => s.focusNow);
  const tempo = useFocusStore((s) => s.tempo);
  const focusFilter = composeFocusFilters({ focusNow, tempo });

  const onlyFav = useFavoritesStore((s) => s.onlyFavorites);
  const favIdsMap = useFavoritesStore((s) => s.ids);
  const favIds = Object.keys(favIdsMap);
  const favFilter = onlyFav ? composeFavoritesFilters(favIds) : "";

  const filters = [focusFilter, favFilter]
    .filter(Boolean)
    .map((f) => `(${f})`)
    .join(" AND ");

  useKeyboardShortcuts();

  return (
    <InstantSearch
      searchClient={searchClient}
      indexName={INDEX_NAME}
      routing={{ router: history() }}
      future={{ preserveSharedStateOnUnmount: true }}
    >
      <Configure hitsPerPage={20} filters={filters || undefined} />
      <header className="app-header">
        <div className="masthead">
          <div className="masthead-stamp">Het Archief</div>
          <h1 className="masthead-title">
            <span className="masthead-title-main">De School</span>
            <span className="masthead-title-sub">Amsterdam</span>
          </h1>
          <div className="masthead-tomb">
            <span>2016</span>
            <span className="tomb-dash" aria-hidden>—</span>
            <span>2024</span>
            <span className="tomb-sep">·</span>
            <span>891 sets</span>
            <span className="tomb-sep">·</span>
            <span className="tomb-note">a polytechnic, not a club</span>
          </div>
        </div>
        <SearchBox
          placeholder="search faculty, curriculum, departments…"
          className="search-box"
        />
      </header>

      {!hasCredentials && (
        <div className="notice">
          Set <code>VITE_ALGOLIA_APP_ID</code> and{" "}
          <code>VITE_ALGOLIA_SEARCH_API_KEY</code> in <code>site/.env</code> to
          connect.
        </div>
      )}

      <section className="timeline-section">
        <YearTimeline />
      </section>

      <FocusStrip />

      <SchoolMap />

      <div className="layout">
        <aside className="filters">
          <section className="facet-section">
            <h3>Curriculum</h3>
            <p className="facet-hint">
              recurring event series
              <span className="facet-hint-mech"> · select one or more</span>
            </p>
            <CountedRefinementList
              attribute="event"
              limit={10}
              searchable
              searchablePlaceholder="search events…"
            />
          </section>
          <section className="facet-section">
            <h3>Faculty</h3>
            <p className="facet-hint">
              the artists who taught
              <span className="facet-hint-mech"> · select one or more</span>
            </p>
            <CountedRefinementList
              attribute="artists"
              limit={10}
              searchable
              searchablePlaceholder="search artists…"
            />
          </section>
          <section className="facet-section">
            <h3>Marginalia</h3>
            <p className="facet-hint">
              tags noted in the catalog
              <span className="facet-hint-mech"> · select one or more</span>
            </p>
            <CountedRefinementList
              attribute="tags"
              limit={10}
              formatLabel={capitalize}
            />
          </section>
        </aside>

        <main className="results">
          <div className="results-toolbar">
            <Stats
              translations={{
                rootElementText: ({ nbHits }) =>
                  `${nbHits.toLocaleString("nl-NL")} set${nbHits === 1 ? "" : "s"} on file`,
              }}
            />
            <FavoritesToggle />
            <SortBy
              items={[
                { value: INDEX_NAME, label: "by relevance" },
                { value: `${INDEX_NAME}_newest`, label: "newest first" },
                { value: `${INDEX_NAME}_oldest`, label: "oldest first" },
              ]}
            />
          </div>
          <Hits hitComponent={Hit} />
          <Pagination />
        </main>
      </div>

      <Player />
      <ArtistModal />
    </InstantSearch>
  );
}

export default App;
