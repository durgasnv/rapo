import { EventList } from "../../components/event-list";
export default function Events() {
  return (
    <main className="page-shell">
      <h1>Meet your next collaborators.</h1>
      <p className="intro">Explore upcoming events from your community.</p>
      <EventList />
    </main>
  );
}
