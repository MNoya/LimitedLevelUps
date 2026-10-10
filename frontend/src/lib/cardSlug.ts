export function cardSlug(name: string): string {
  return frontFace(name)
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function frontFace(name: string): string {
  return name.split("//")[0].trim();
}
