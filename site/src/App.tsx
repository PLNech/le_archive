import { useState } from "react";
import {
  InstantSearch,
  SearchBox,
  Hits,
  Pagination,
  Stats,
  SortBy,
  Configure,
  RangeInput,
} from "react-instantsearch";
import { history } from "instantsearch.js/es/lib/routers";
import { searchClient, INDEX_NAME, hasCredentials } from "./lib/algolia";
import { Hit } from "./components/Hit";
import { Player } from "./components/Player";
import { SimilarStrip } from "./components/SimilarStrip";
import { CountedRefinementList } from "./components/CountedRefinementList";
import { YearTimeline } from "./components/YearTimeline";
import { SchoolMap } from "./components/SchoolMap";
import { ArtistModal } from "./components/ArtistModal";
import { FocusStrip } from "./components/FocusStrip";
import { FavoritesToggle } from "./components/FavoritesToggle";
import { QueueToggle } from "./components/QueueToggle";
import { QueueBridge } from "./components/QueueBridge";
import { DebugStrip } from "./components/DebugStrip";
import { ThemeToggle } from "./components/ThemeToggle";
import { Colophon } from "./components/Colophon";
import { ScrollProgress } from "./components/ScrollProgress";
import { MobileFilters } from "./components/MobileFilters";
import { useApplyTheme } from "./hooks/useThemeStore";
import { useFocusStore, composeFocusFilters } from "./hooks/useFocusStore";
import {
  useFavoritesStore,
  composeFavoritesFilters,
} from "./hooks/useFavoritesStore";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useDebugStore } from "./hooks/useDebugStore";
import { flagFilter } from "./hooks/useEnrichmentCoverage";
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

  const debugFlags = useDebugStore((s) => s.activeFlags);
  const debugFilter = flagFilter(debugFlags);

  const filters = [focusFilter, favFilter, debugFilter]
    .filter(Boolean)
    .map((f) => `(${f})`)
    .join(" AND ");

  useKeyboardShortcuts();
  useApplyTheme();

  const [filtersOpen, setFiltersOpen] = useState(false);
  const focusActive = focusNow || tempo !== "any";
  const activeFilterCount =
    (focusActive ? 1 : 0) + (onlyFav ? 1 : 0) + debugFlags.length;

  return (
    <InstantSearch
      searchClient={searchClient}
      indexName={INDEX_NAME}
      routing={{ router: history() }}
      future={{ preserveSharedStateOnUnmount: true }}
    >
      <Configure hitsPerPage={20} filters={filters || undefined} />
      <ScrollProgress />
      <header className="app-header">
        <div className="masthead">
          <ThemeToggle />
          <div className="masthead-stamp">Het Archief</div>
          <h1 className="masthead-title">
            <span className="masthead-accession" aria-hidden>
              ARCH.&nbsp;016–024 · VOL.&nbsp;I
            </span>
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

      <section className="overview-row">
        <div className="overview-timeline">
          <YearTimeline />
        </div>
        <div className="overview-map">
          <SchoolMap />
        </div>
      </section>

      <FocusStrip />
      <DebugStrip />

      <MobileFilters
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        onClose={() => setFiltersOpen(false)}
        activeCount={activeFilterCount}
      />

      <div className={`layout ${filtersOpen ? "layout--filters-open" : ""}`}>
        <aside
          id="site-filters"
          className={`filters ${filtersOpen ? "filters--open" : ""}`}
        >
          <div className="filters-sheet-handle" aria-hidden>
            <span className="filters-sheet-grip" />
          </div>
          <div className="filters-sheet-head">
            <span className="filters-sheet-title">Filters</span>
            <button
              type="button"
              className="filters-sheet-close"
              onClick={() => setFiltersOpen(false)}
              aria-label="close filters"
            >
              ✕
            </button>
          </div>
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
            <h3>Genres</h3>
            <p className="facet-hint">
              from the faculty's canon
              <span className="facet-hint-mech"> · select one or more</span>
            </p>
            <CountedRefinementList
              attribute="artist_genres"
              limit={10}
              searchable
              searchablePlaceholder="search genres…"
              formatLabel={capitalize}
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
          <section className="facet-section">
            <h3>Length</h3>
            <p className="facet-hint">
              short · medium · long
              <span className="facet-hint-mech"> · single pick</span>
            </p>
            <CountedRefinementList
              attribute="duration_bucket"
              limit={5}
              formatLabel={capitalize}
            />
          </section>
          <section className="facet-section">
            <h3>Tempo</h3>
            <p className="facet-hint">
              pace bucket from beat-tracking
              <span className="facet-hint-mech"> · single pick</span>
            </p>
            <CountedRefinementList
              attribute="tempo_bucket"
              limit={5}
              formatLabel={capitalize}
            />
          </section>
          <section className="facet-section">
            <h3>BPM</h3>
            <p className="facet-hint">
              tempo range
              <span className="facet-hint-mech"> · numeric</span>
            </p>
            <RangeInput attribute="bpm" precision={0} />
          </section>
          <section className="facet-section">
            <h3>Energy</h3>
            <p className="facet-hint">
              loudness mean (0 = silent, 1 = peak)
              <span className="facet-hint-mech"> · numeric</span>
            </p>
            <RangeInput attribute="energy_mean" precision={3} />
          </section>
          <section className="facet-section">
            <h3>Brightness</h3>
            <p className="facet-hint">
              spectral centroid — high = airy
              <span className="facet-hint-mech"> · numeric</span>
            </p>
            <RangeInput attribute="brightness" precision={3} />
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
            <QueueToggle />
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

      <Colophon />

      <QueueBridge />
      <Player />
      <SimilarStrip />
      <ArtistModal />
    </InstantSearch>
  );
}

export default App;
