/**
 * Prepara a foto escolhida no celular antes do envio: recorta um quadrado no
 * centro e reduz para 512x512 em JPEG. Fica leve para enviar até em 3G; o
 * servidor ainda reprocessa (256x256) e apaga os metadados.
 * Lança Error com mensagem em português se o navegador não conseguir ler a imagem.
 */
export async function prepararFoto(arquivo: File, lado = 512): Promise<Blob> {
  if (!arquivo.type.startsWith("image/")) {
    throw new Error("Escolha um arquivo de imagem.");
  }
  const url = URL.createObjectURL(arquivo);
  try {
    const img = new Image();
    img.src = url;
    try {
      await img.decode();
    } catch {
      throw new Error("Não consegui abrir essa foto. Tente uma imagem JPG ou PNG.");
    }
    const menor = Math.min(img.naturalWidth, img.naturalHeight);
    const sx = (img.naturalWidth - menor) / 2;
    const sy = (img.naturalHeight - menor) / 2;
    const destino = Math.min(lado, menor);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = destino;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Seu navegador não conseguiu preparar a foto.");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, destino, destino);
    ctx.drawImage(img, sx, sy, menor, menor, 0, 0, destino, destino);
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", 0.9));
    if (!blob) throw new Error("Seu navegador não conseguiu preparar a foto.");
    return blob;
  } finally {
    URL.revokeObjectURL(url);
  }
}
