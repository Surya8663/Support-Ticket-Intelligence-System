import { useState } from "react";
import { api } from "../api";
import type { QueryResult } from "../types";

const SAMPLES = [
  "How many tickets are currently open?",
  "Which agent resolved the most tickets this month?",
  "Show me all Critical tickets not resolved within 12 hours.",
  "What is the average customer rating for Technical category tickets?",
  "Are there any anomalies in resolution times this week?",
];

export function Ask() {
  const [question, setQuestion] = useState(SAMPLES[0]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(next = question) {
    setBusy(true);
    setError("");
    try {
      setResult(await api.query(next));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1 className="page-title">Ask the data</h1>
      <p className="lede">
        Groq translates the question to SQLite. Numbers come from the database, not the model. Generated
        SQL is always shown so a bad translation is visible.
      </p>
      <div className="chips">
        {SAMPLES.map((sample) => (
          <button
            key={sample}
            className={`chip ${sample === question ? "active" : ""}`}
            type="button"
            onClick={() => setQuestion(sample)}
          >
            {sample}
          </button>
        ))}
      </div>
      <form
        className="form-stack"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <label htmlFor="question">Question</label>
        <textarea
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <div>
          <button className="btn btn-primary" type="submit" disabled={busy || question.trim().length < 3}>
            {busy ? "Translating…" : "Run query"}
          </button>
        </div>
      </form>
      {error ? <div className="banner error" style={{ marginTop: 16 }}>{error}</div> : null}
      {result ? (
        <article className="panel" style={{ marginTop: 20 }}>
          <h2>Answer</h2>
          <p>{result.answer}</p>
          <p className="lede">{result.explanation}</p>
          <p className="lede">{result.row_count} matching row(s)</p>
          <pre className="sql">{result.sql}</pre>
          {result.rows.length ? (
            <div className="table-wrap" style={{ marginTop: 16 }}>
              <table>
                <thead>
                  <tr>
                    {Object.keys(result.rows[0]).map((key) => (
                      <th key={key}>{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr key={index}>
                      {Object.values(row).map((value, cell) => (
                        <td key={cell}>{value == null ? "—" : String(value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </article>
      ) : null}
    </section>
  );
}
