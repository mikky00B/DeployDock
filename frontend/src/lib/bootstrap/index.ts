import type { Server } from "../../types/server";
import {
  applyDjangoBootstrapDefaults,
  createEmptyBootstrapDjangoForm,
  generateDjangoBootstrapPlan,
  type BootstrapDjangoForm,
} from "./django";
import { stackDescriptions, stackLabels, slugify, type BootstrapPlan, type BootstrapStack } from "./common";
import {
  applyFastApiBootstrapDefaults,
  createEmptyBootstrapFastApiForm,
  generateFastApiBootstrapPlan,
  type BootstrapFastApiForm,
} from "./fastapi";
import {
  applyGoBootstrapDefaults,
  createEmptyBootstrapGoForm,
  generateGoBootstrapPlan,
  type BootstrapGoForm,
} from "./go";
import {
  applyStaticSiteBootstrapDefaults,
  createEmptyBootstrapStaticSiteForm,
  generateStaticSiteBootstrapPlan,
  type BootstrapStaticSiteForm,
} from "./staticSite";

export { stackDescriptions, stackLabels, slugify };
export type { BootstrapPlan, BootstrapPlanSection, BootstrapStack } from "./common";
export type { BootstrapDjangoForm } from "./django";
export type { BootstrapFastApiForm } from "./fastapi";
export type { BootstrapGoForm } from "./go";
export type { BootstrapStaticSiteForm } from "./staticSite";

export type BootstrapForm =
  | (BootstrapDjangoForm & { stack: "django" })
  | BootstrapFastApiForm
  | BootstrapGoForm
  | BootstrapStaticSiteForm;

export function createEmptyBootstrapForm(stack: BootstrapStack = "django", serverId = ""): BootstrapForm {
  switch (stack) {
    case "fastapi":
      return createEmptyBootstrapFastApiForm(serverId);
    case "go":
      return createEmptyBootstrapGoForm(serverId);
    case "static":
      return createEmptyBootstrapStaticSiteForm(serverId);
    case "django":
      return { ...createEmptyBootstrapDjangoForm(serverId), stack: "django" };
  }
}

export function applyBootstrapDefaults(form: BootstrapForm): BootstrapForm {
  switch (form.stack) {
    case "fastapi":
      return applyFastApiBootstrapDefaults(form);
    case "go":
      return applyGoBootstrapDefaults(form);
    case "static":
      return applyStaticSiteBootstrapDefaults(form);
    case "django":
      return { ...applyDjangoBootstrapDefaults(form), stack: "django" };
  }
}

export function generateBootstrapPlan(form: BootstrapForm, servers: Server[]): BootstrapPlan {
  switch (form.stack) {
    case "fastapi":
      return generateFastApiBootstrapPlan(form, servers);
    case "go":
      return generateGoBootstrapPlan(form, servers);
    case "static":
      return generateStaticSiteBootstrapPlan(form, servers);
    case "django": {
      const plan = generateDjangoBootstrapPlan(form, servers);
      return {
        stack: "django",
        stackLabel: stackLabels.django,
        stackDescription: stackDescriptions.django,
        sections: plan.sections,
        appPayload: plan.appPayload,
      };
    }
  }
}
