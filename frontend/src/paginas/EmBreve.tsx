type Props = {
  titulo: string;
  semana: number;
};

export function EmBreve({ titulo, semana }: Props) {
  return (
    <section className="em-breve">
      <h1>{titulo}</h1>
      <p>Chega na semana {semana}.</p>
    </section>
  );
}
