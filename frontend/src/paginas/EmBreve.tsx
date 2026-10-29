type Props = {
  titulo: string;
  semana: number;
};

/** Área que ainda não existe, com a semana do plano em que ela chega. */
export function EmBreve({ titulo, semana }: Props) {
  return (
    <section className="em-breve">
      <h1>{titulo}</h1>
      <p>Chega na semana {semana}.</p>
    </section>
  );
}
