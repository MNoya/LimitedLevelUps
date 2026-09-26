import { useLocation, useNavigate, type To } from "react-router-dom";

export const OPENED_IN_APP = { openedInApp: true };

export const useCloseModal = (fallback: To) => {
  const navigate = useNavigate();
  const location = useLocation();
  const openedInApp = (location.state as typeof OPENED_IN_APP | null)?.openedInApp === true;
  return () => {
    if (openedInApp) {
      navigate(-1);
      return;
    }
    navigate(fallback, { replace: true });
  };
};
