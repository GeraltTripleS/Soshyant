import { module } from "@prisma/composer";
import webService from "./src/service.ts";

// "soshyant-landing" becomes the project name in the Prisma Console.
export default module("soshyant-landing", ({ provision }) => {
  provision(webService);
});
