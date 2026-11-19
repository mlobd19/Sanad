// Logo « khaïma » : la tente mauritanienne, l'abri qui protège.

type Props = { size?: number; color?: string; sun?: string; title?: string };

export function KhaimaMark({ size = 32, color = "var(--green)", sun = "var(--sand)", title }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <circle cx="76" cy="22" r="7" fill={sun} />
      <path
        d="M12 74C28 66 36 44 48 16C60 44 68 66 84 74"
        fill="none"
        stroke={color}
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M39 76C41 64 44 57 48 54C52 57 55 64 57 76z" fill={color} />
      <path d="M8 82h80" stroke={color} strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <span className="wordmark" style={{ fontSize: size }}>
      <KhaimaMark size={size * 1.5} />
      {name}
    </span>
  );
}
