declare module "page-flip" {
  export type PageFlipEvent = { data: number | string };

  export class PageFlip {
    constructor(element: HTMLElement, settings: Record<string, string | number | boolean>);
    loadFromHTML(elements: NodeListOf<HTMLElement> | HTMLElement[]): void;
    on(event: string, callback: (event: PageFlipEvent) => void): void;
    flipNext(corner?: "top" | "bottom"): void;
    flipPrev(corner?: "top" | "bottom"): void;
    flip(page: number, corner?: "top" | "bottom"): void;
    turnToNextPage(): void;
    turnToPrevPage(): void;
    turnToPage(page: number): void;
    getCurrentPageIndex(): number;
    getPageCount(): number;
    update(): void;
    destroy(): void;
  }
}
