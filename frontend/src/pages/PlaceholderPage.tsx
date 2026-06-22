type PlaceholderPageProps = {
  title: string;
};

export function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <section className="empty-panel" aria-labelledby="placeholder-title">
      <h2 id="placeholder-title">{title}</h2>
      <p>This workspace opens in the next frontend milestone.</p>
    </section>
  );
}
