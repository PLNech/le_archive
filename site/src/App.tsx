import {
  InstantSearch,
  SearchBox,
  Hits,
  RefinementList,
  Pagination,
  Stats,
  SortBy,
  Configure,
} from "react-instantsearch";
import { searchClient, INDEX_NAME, hasCredentials } from "./lib/algolia";
import { Hit } from "./components/Hit";
import { Player } from "./components/Player";
import "./App.css";

function App() {
  return (
    <InstantSearch searchClient={searchClient} indexName={INDEX_NAME}>
      <Configure hitsPerPage={20} />
      <header className="app-header">
        <h1>LeArchive</h1>
        <p className="tagline">De School Amsterdam · 2016–2024</p>
        <SearchBox
          placeholder="search artists, events, spaces…"
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

      <div className="layout">
        <aside className="filters">
          <section>
            <h3>year</h3>
            <RefinementList attribute="year" limit={10} sortBy={["name:desc"]} />
          </section>
          <section>
            <h3>space</h3>
            <RefinementList attribute="space" limit={10} />
          </section>
          <section>
            <h3>event</h3>
            <RefinementList attribute="event" limit={10} searchable />
          </section>
          <section>
            <h3>artist</h3>
            <RefinementList attribute="artists" limit={10} searchable />
          </section>
          <section>
            <h3>tags</h3>
            <RefinementList attribute="tags" limit={10} />
          </section>
        </aside>

        <main className="results">
          <div className="results-toolbar">
            <Stats />
            <SortBy
              items={[
                { value: INDEX_NAME, label: "relevance" },
                { value: `${INDEX_NAME}_newest`, label: "newest" },
                { value: `${INDEX_NAME}_oldest`, label: "oldest" },
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
