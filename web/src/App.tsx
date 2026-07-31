import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { router } from "./routes/router";
import { queryClient } from "./api/queryClient";
import { ThemeModeProvider } from "./theme/ThemeModeProvider";
import { bootstrapSession } from "./api/client";

export function App() {
  useEffect(() => {
    bootstrapSession();
  }, []);

  return (
    <ThemeModeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeModeProvider>
  );
}
