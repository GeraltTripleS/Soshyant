import { defineConfig as composer } from "@prisma/composer/config";
import { nodeBuild } from "@prisma/composer/node/control";
import { prismaCloud, prismaState } from "@prisma/composer-prisma-cloud/control";
import { definePrismaConfig } from "prisma/config";

export default definePrismaConfig({
  composer: composer({
    // Paris. Only used for the first deploy; an existing project keeps its region.
    extensions: [prismaCloud({ region: "eu-west-3" }), nodeBuild()],
    state: prismaState(),
  }),
});
