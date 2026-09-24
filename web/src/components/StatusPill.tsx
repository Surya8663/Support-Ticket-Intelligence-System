type Props = { value: string };

export function StatusPill({ value }: Props) {
  const key = value.toLowerCase();
  return <span className={`pill ${key}`}>{value}</span>;
}
