// Python Tools for Visual Studio
// Copyright(c) Microsoft Corporation
// All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the License); you may not use
// this file except in compliance with the License. You may obtain a copy of the
// License at http://www.apache.org/licenses/LICENSE-2.0
//
// THIS CODE IS PROVIDED ON AN  *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS
// OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY
// IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
// MERCHANTABILITY OR NON-INFRINGEMENT.
//
// See the Apache Version 2.0 License for specific language governing
// permissions and limitations under the License.

using System.Windows.Automation;

namespace TestUtilities.UI.Python {
    public class PythonInstallPackagesInfoBar : AutomationWrapper {
        private const string InstallPackagesAutomationName = "Install packages";
        private const string DoNotShowAgainAutomationName = "Don't show this message again";

        public PythonInstallPackagesInfoBar(AutomationElement element)
            : base(element) {
        }

        public static Condition FindCondition = new AndCondition(
            new PropertyCondition(AutomationElement.NameProperty, InstallPackagesAutomationName),
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Hyperlink)
        );

        public void InstallPackages() {
            ClickHyperlinkByName(InstallPackagesAutomationName);
        }

        public void DoNotShowAgain() {
            ClickHyperlinkByName(DoNotShowAgainAutomationName);
        }
    }
}
