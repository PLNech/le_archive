import {
  InstantSearch,
  SearchBox,
  Hits,
  Pagination,
  Stats,
  SortBy,
  Configure,
} from "react-instantsearch";
import { searchClient, INDEX_NAME, hasCredentials } from "./lib/algolia";
import { Hit } from "./components/Hit";
import { Player } from "./components/Player";
import { CountedRefinementList } from "./components/CountedRefinementList";
import { YearTimeline } from "./components/YearTimeline";
import "./App.css";

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function App() {
  return (
    <InstantSearch searchClient={searchClient} indexName={INDEX_NAME}>
      <Configure hitsPerPage={20} />
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

      <div className="layout">
        <aside className="filters">
          <section className="facet-section">
            <h3>Departments</h3>
            <p className="facet-hint">physical rooms of the school</p>
            <CountedRefinementList attribute="space" limit={12} />
          </section>
          <section className="facet-section">
            <h3>Curriculum</h3>
            <p className="facet-hint">recurring event series</p>
            <CountedRefinementList
              attribute="event"
              limit={10}
              searchable
              searchablePlaceholder="search events…"
            />
          </section>
          <section className="facet-section">
            <h3>Faculty</h3>
            <p className="facet-hint">the artists who taught</p>
            <CountedRefinementList
              attribute="artists"
              limit={10}
              searchable
              searchablePlaceholder="search artists…"
            />
          </section>
          <section className="facet-section">
            <h3>Marginalia</h3>
            <p className="facet-hint">tags noted in the catalog</p>
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
    </InstantSearch>
  );
}

export default App;
