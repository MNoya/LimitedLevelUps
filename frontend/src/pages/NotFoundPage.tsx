import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { CtaPill } from "../components/CtaPill";

export function NotFoundPage() {
  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="" />
      <main className="flex-1 flex flex-col items-center justify-center text-center px-5 gap-6 md:gap-7">
        <div className="flex flex-col gap-3">
          <h1 className="font-display text-green leading-none tracking-[0.1em] text-[44px] md:text-[68px]">
            PAGE NOT FOUND
          </h1>
          <div className="flex flex-col gap-2 text-[14px] md:text-[15px] leading-[1.6] max-w-[440px]">
            <p className="text-text">Oops! The page you were looking for could not be resolved.</p>
            <p className="text-muted">It may have been moved, or the link was mistyped.</p>
          </div>
        </div>
        <Link to="/" className="no-underline">
          <CtaPill size="md">BACK TO HOME</CtaPill>
        </Link>
      </main>
      <Footer className="px-5 md:px-10 pb-5" />
    </div>
  );
}
